"""Column threshold watcher — deterministic checks, no LLM.

Consumer group 'column-watchers' on plant:telemetry.
Monitors column operating envelopes (distillate, bottoms, reboiler, flooding).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from plantmind_core.bus import RedisBus
from plantmind_core.telemetry import get_logger

log = get_logger("watchers.column")

STREAM = "plant:telemetry"
ALERT_STREAM = "alerts:critical"
GROUP = "column-watchers"
CONSUMER = "column-watcher-1"
BLOCK_MS = 10_000
DEBOUNCE_S = 30

_REPO_CONFIG = Path(__file__).resolve().parents[3] / "config" / "tep_envelopes.json"
_CONTAINER_CONFIG = Path("/srv/config/tep_envelopes.json")
_ENVELOPE_PATH = _CONTAINER_CONFIG if _CONTAINER_CONFIG.exists() else _REPO_CONFIG


def _load_fallback_envelopes() -> dict:
    if _ENVELOPE_PATH.exists():
        with open(_ENVELOPE_PATH) as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    return {}


class ColumnWatcher:
    def __init__(self, bus: RedisBus):
        self._bus = bus
        self._envelopes = self._load_initial_envelopes()
        self._open: dict[str, dict] = {}

    @classmethod
    def from_settings(cls) -> "ColumnWatcher":
        return cls(RedisBus.from_settings())

    def _load_initial_envelopes(self) -> dict:
        try:
            cached = self._bus._r.hgetall("sim:limits")
            if cached:
                log.info("loaded initial column limits from Redis sim:limits")
                return {k: json.loads(v) for k, v in cached.items()}
        except Exception as e:
            log.warning("failed to load initial column limits from Redis, using json fallback", error=str(e))
        return _load_fallback_envelopes()

    def _start_limits_listener(self):
        try:
            p = self._bus._r.pubsub()
            p.subscribe(**{"sim:limits:reload": self._on_limits_reload})
            p.run_in_thread(sleep_time=1.0, daemon=True)
            log.info("started background column limits reload listener")
        except Exception as e:
            log.warning("failed to start column limits pubsub listener", error=str(e))

    def _on_limits_reload(self, message):
        try:
            data = json.loads(message["data"])
            tag_id = data["tag_id"]
            limits = data["limits"]
            self._envelopes[tag_id] = limits
            log.info("live-reloaded column limits for tag", tag_id=tag_id, limits=limits)
        except Exception as e:
            log.warning("failed to parse column limits reload payload", error=str(e))

    def run(self):
        log.info("column watcher started", stream=STREAM, group=GROUP)
        self._ensure_group()
        self._start_limits_listener()
        while True:
            self._tick()

    def _ensure_group(self):
        try:
            self._bus._r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
        except Exception:
            pass

    def _tick(self):
        entries = self._bus._r.xreadgroup(
            GROUP, CONSUMER, {STREAM: ">"}, count=100, block=BLOCK_MS
        )
        if not entries:
            return
        for _stream, messages in entries:
            for entry_id, fields in messages:
                try:
                    self._on_message(fields)
                except Exception as exc:
                    log.warning("column watcher error on message", error=str(exc)[:120])
                finally:
                    self._bus._r.xack(STREAM, GROUP, entry_id)

    def _on_message(self, fields: dict):
        tag_id = fields.get("tag_id", "")
        raw_value = fields.get("value", "")
        status = fields.get("status", "GOOD")

        if not tag_id or tag_id not in self._envelopes:
            return

        env = self._envelopes[tag_id]

        if status == "BAD":
            self._fire(tag_id, "STATUS_BAD", float("nan"), float("nan"), "BAD column sensor reading")
            return
        elif status == "UNCERTAIN":
            self._fire(tag_id, "STATUS_UNCERTAIN", float("nan"), float("nan"), "UNCERTAIN column sensor reading quality")

        try:
            value = float(raw_value)
        except ValueError:
            return

        hh = env.get("hh", env.get("max"))
        h = env.get("h")
        ll = env.get("ll", env.get("min"))
        l = env.get("l")

        if hh is not None and value > hh:
            self._fire(tag_id, "HH_EXCEEDED", value, hh, f"{tag_id} = {value:.4f} {env.get('unit','')} > High-High limit {hh}")
        elif h is not None and value > h:
            self._fire(tag_id, "H_EXCEEDED", value, h, f"{tag_id} = {value:.4f} {env.get('unit','')} > High limit {h}")
        else:
            self._maybe_close(tag_id, "HH_EXCEEDED", value, env)
            self._maybe_close(tag_id, "H_EXCEEDED", value, env)

        if ll is not None and value < ll:
            self._fire(tag_id, "LL_EXCEEDED", value, ll, f"{tag_id} = {value:.4f} {env.get('unit','')} < Low-Low limit {ll}")
        elif l is not None and value < l:
            self._fire(tag_id, "L_EXCEEDED", value, l, f"{tag_id} = {value:.4f} {env.get('unit','')} < Low limit {l}")
        else:
            self._maybe_close(tag_id, "LL_EXCEEDED", value, env)
            self._maybe_close(tag_id, "L_EXCEEDED", value, env)

    def _maybe_close(self, tag_id: str, rule: str, value: float, env: dict):
        fp = f"column:{tag_id}:{rule}"
        if fp in self._open and self._open[fp]["in_breach"]:
            state = self._open[fp]
            if time.time() - state["last_seen"] >= DEBOUNCE_S:
                log.info("column alert auto-closed", tag_id=tag_id, rule=rule)
                self._open[fp]["in_breach"] = False

    def _fire(self, tag_id: str, rule: str, value: float, threshold: float, body: str):
        fingerprint = f"column:{tag_id}:{rule}"
        now = time.time()
        severity = "critical" if rule in ("HH_EXCEEDED", "LL_EXCEEDED", "STATUS_BAD") else "warning"

        if fingerprint in self._open and self._open[fingerprint]["in_breach"]:
            state = self._open[fingerprint]
            state["last_seen"] = now
            if abs(value) > abs(state.get("peak_value", value)):
                state["peak_value"] = value
            return

        self._open[fingerprint] = {
            "in_breach": True,
            "first_seen": now,
            "last_seen": now,
            "peak_value": value,
        }

        equipment = tag_id.split(".")[0]
        alert_payload = {
            "kind": "process_limit",
            "severity": severity,
            "title": f"Column process breach: {tag_id} \u2014 {rule}",
            "body": body,
            "equipment": equipment,
            "citations": [],
            "web_sources": [],
            "fingerprint": fingerprint,
            "graph_version": self._bus.graph_version(),
            "verified": True,
            "unverified_claims": [],
            "tag_id": tag_id,
            "rule": rule,
            "value": value if value == value else None,
            "threshold": threshold,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._bus.publish_alert(json.dumps(alert_payload))
        log.info("column alert opened", tag_id=tag_id, rule=rule, value=value, severity=severity)


def main():
    ColumnWatcher.from_settings().run()


if __name__ == "__main__":
    main()
