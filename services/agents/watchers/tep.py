"""TEP threshold watcher — ISA 18.2 envelope checks for TEP tags.

Consumes plant:telemetry Redis stream, checks all MV/PV tags against
the TEP operating envelopes, and fires alerts:critical on breach.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from plantmind_core.bus import RedisBus
from plantmind_core.telemetry import get_logger

log = get_logger("watchers.tep")

STREAM = "plant:telemetry"
ALERT_STREAM = "alerts:critical"
GROUP = "tep-watchers"
CONSUMER = "tep-watcher-1"
BLOCK_MS = 10_000
DEBOUNCE_S = 30
# the simulator announces a reset here; every open alarm is dropped so the
# next injected fault alarms again instead of being swallowed as "already open"
RESET_CHANNEL = "sim:reset"

_REPO_CONFIG = Path(__file__).resolve().parents[3] / "config" / "tep_envelopes.json"
_CONTAINER_CONFIG = Path("/srv/config/tep_envelopes.json")
_ENVELOPE_PATH = _CONTAINER_CONFIG if _CONTAINER_CONFIG.exists() else _REPO_CONFIG


def _load_fallback_envelopes() -> dict:
    with open(_ENVELOPE_PATH) as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


class TepWatcher:
    def __init__(self, bus: RedisBus):
        self._bus = bus
        self._envelopes = self._load_initial_envelopes()
        self._prev: dict[str, tuple[float, float]] = {}
        self._open: dict[str, dict] = {}

    @classmethod
    def from_settings(cls) -> "TepWatcher":
        return cls(RedisBus.from_settings())

    def _load_initial_envelopes(self) -> dict:
        try:
            cached = self._bus._r.hgetall("sim:limits")
            if cached:
                log.info("loaded initial TEP limits from Redis sim:limits")
                return {k: json.loads(v) for k, v in cached.items()}
        except Exception as e:
            log.warning("failed to load TEP limits from Redis, using json fallback", error=str(e))
        return _load_fallback_envelopes()

    def _start_limits_listener(self):
        try:
            p = self._bus._r.pubsub()
            p.subscribe("sim:limits:reload", RESET_CHANNEL)
            import threading

            def _listen():
                for msg in p.listen():
                    if msg["type"] != "message":
                        continue
                    if msg["channel"] == RESET_CHANNEL:
                        self.rearm_all("simulator reset")
                        continue
                    try:
                        data = json.loads(msg["data"])
                        tag_id = data.get("tag_id")
                        limits = data.get("limits")
                        if tag_id and limits:
                            self._envelopes[tag_id] = limits
                            log.info("live limits updated", tag_id=tag_id)
                    except Exception as e:
                        log.warning("limits reload error", error=str(e))

            threading.Thread(target=_listen, daemon=True).start()
        except Exception as e:
            log.warning("could not start limits listener", error=str(e))

    def _ensure_group(self):
        try:
            self._bus._r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
        except Exception:
            pass

    def _level_for(self, value: float, env: dict) -> str | None:
        hh = env.get("hh")
        h = env.get("h")
        l = env.get("l")
        ll = env.get("ll")
        if hh is not None and value >= hh:
            return "HH"
        if h is not None and value >= h:
            return "H"
        if ll is not None and value <= ll:
            return "LL"
        if l is not None and value <= l:
            return "L"
        return None

    def _check_message(self, fields: dict):
        tag_id = fields.get("tag_id", "")
        env = self._envelopes.get(tag_id)
        if env is None:
            return

        try:
            value = float(fields.get("value", "0"))
        except ValueError:
            return

        ts = time.time()
        level = self._level_for(value, env)

        # Open alarms are keyed by TAG, not by tag+level. Keying them by
        # tag+level is what broke re-arming: the return-to-normal branch has no
        # level to build that key from, so it looked up "<tag>:None", never
        # found it, and the entry stayed open for the life of the process. A
        # tag that alarmed once then recovered could never alarm again, which
        # is why a second IDV injection produced no alert. Per-tag also gives
        # escalation for free — H -> HH is a state change on the same alarm.
        open_alarm = self._open.get(tag_id)

        if level is not None:
            if open_alarm is None or open_alarm["level"] != level:
                self._open[tag_id] = {
                    "first_seen": ts,
                    "last_seen": ts,
                    "peak_value": value,
                    "tag_id": tag_id,
                    "level": level,
                    "env": env,
                    "cleared_at": None,
                }
                self._fire_alert(tag_id, value, level, env, ts)
                return

            open_alarm["last_seen"] = ts
            open_alarm["cleared_at"] = None      # dipped back in, still breached
            peak = open_alarm["peak_value"]
            if level in ("HH", "H") and value > peak:
                open_alarm["peak_value"] = value
            elif level in ("LL", "L") and value < peak:
                open_alarm["peak_value"] = value
            return

        # Back inside the envelope. Re-arm only after the value has stayed in
        # for DEBOUNCE_S, so a tag chattering across a limit does not produce
        # one alert per crossing. The clock starts when the breach ended, not
        # when it was last seen breaching.
        if open_alarm is None:
            return
        if open_alarm["cleared_at"] is None:
            open_alarm["cleared_at"] = ts
        elif ts - open_alarm["cleared_at"] >= DEBOUNCE_S:
            del self._open[tag_id]
            log.info("TEP alarm cleared and re-armed", tag_id=tag_id,
                     alarm_level=open_alarm["level"])

    def rearm_all(self, reason: str = "reset"):
        """Drop every open alarm so the next breach fires fresh.

        Called when the simulator is reset: the process goes back to nominal
        without the watcher ever seeing an in-envelope sample for the tags that
        were breaching, so without this the alarms they left open would suppress
        the alerts from the next fault injected after a reset."""
        count = len(self._open)
        self._open.clear()
        log.info("TEP watcher re-armed", cleared=count, reason=reason)

    def _fire_alert(self, tag_id: str, value: float, level: str, env: dict, ts: float):
        unit_area = tag_id.split(".")[0] if "." in tag_id else tag_id
        setpoint = env.get("setpoint")
        limit_val = env.get(
            level.lower(),
            env.get({"HH": "hh", "H": "h", "L": "l", "LL": "ll"}.get(level, "h"), None),
        )

        severity = {"HH": "critical", "LL": "critical", "H": "warning", "L": "warning"}.get(level, "warning")
        fingerprint = f"tep:{tag_id}:{level}"

        msg_text = (
            f"TEP {unit_area} — {tag_id} {level} alarm: "
            f"value={value:.3f} breached {'>' if level in ('H','HH') else '<'} {limit_val}"
        )
        payload = {
            "title": f"Process Alarm: {tag_id} ({level})",
            "body": (
                f"**Process Limit Breach**: `{tag_id}` reading is **{value:.3f}** "
                f"(limit: **{limit_val}**, setpoint: **{setpoint}**).\n\n"
                f"* **Unit**: {unit_area}\n"
                f"* **Alarm Level**: {level}\n"
                f"* **Severity**: {severity.upper()}"
            ),
            "kind": "process_limit",
            "fingerprint": fingerprint,
            "tag_id": tag_id,
            "unit": unit_area,
            "equipment": unit_area,
            "value": round(value, 4),
            "level": level,
            "limit": limit_val,
            "setpoint": setpoint,
            "severity": severity,
            "timestamp": ts,
            "message": msg_text,
            "verified": True,
        }
        try:
            self._bus._r.xadd(
                ALERT_STREAM,
                {"payload": json.dumps(payload)},
                maxlen=10_000,
                approximate=True,
            )
            log.warning("TEP alarm fired", tag_id=tag_id, alarm_level=level, value=value)
        except Exception as e:
            log.error("failed to publish TEP alarm", error=str(e))

    def run(self):
        self._ensure_group()
        self._start_limits_listener()
        log.info("TEP watcher running", stream=STREAM, group=GROUP)

        while True:
            try:
                reply = self._bus._r.xreadgroup(
                    GROUP, CONSUMER,
                    {STREAM: ">"},
                    block=BLOCK_MS,
                    count=200,
                )
                if not reply:
                    continue
                for _stream, entries in reply:
                    for entry_id, fields in entries:
                        self._check_message(fields)
                        self._bus._r.xack(STREAM, GROUP, entry_id)
            except KeyboardInterrupt:
                log.info("TEP watcher shutting down")
                break
            except Exception as e:
                log.error("TEP watcher loop error", error=str(e))
                time.sleep(2)


def main():
    watcher = TepWatcher.from_settings()
    watcher.run()


if __name__ == "__main__":
    main()
