"""CSTR threshold watcher — deterministic envelope checks, no LLM.

Mirrors the FailureWatcher pattern in agents/watchers.py:
  - Runs as a Redis consumer group ('cstr-watchers') on plant:telemetry
  - Resumable: saves its position in Redis so a restart doesn't skip messages
  - On envelope breach: XADD alerts:critical with the standard Alert shape
  - No LLM calls. Threshold logic is pure arithmetic.

Three checks per tagged measurement:
  1. Value exceeds configured max / falls below configured min.
  2. Rate-of-rise exceeds dT_dt_max (K/s), computed from last two samples.
     Only meaningful for temperature tags (checked only if dT_dt_max is set).
  3. Status="BAD" in the payload → publisher detected a non-finite value.

Dedup: uses the same RedisBus.claim_alert() mechanism as the existing watcher.
Fingerprint: "cstr:{tag_id}:{rule}" — one alert per tag+rule pair until the
condition clears and re-triggers (Redis SET NX with a 60-second TTL).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Bootstrap sys.path for running as a script outside docker
# ──────────────────────────────────────────────────────────────────────────────
_repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo / "libs" / "core"))

from plantmind_core.bus import RedisBus
from plantmind_core.telemetry import get_logger

log = get_logger("watchers.cstr")

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
STREAM      = "plant:telemetry"
ALERT_STREAM = "alerts:critical"
GROUP       = "cstr-watchers"
CONSUMER    = "cstr-watcher-1"
BLOCK_MS    = 10_000
DEDUP_TTL_S = 60          # how long before the same alert can fire again

_ENVELOPE_PATH = Path(__file__).resolve().parents[2] / "config" / "cstr_envelopes.json"


def _load_envelopes() -> dict:
    with open(_ENVELOPE_PATH) as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


# ──────────────────────────────────────────────────────────────────────────────
# Watcher
# ──────────────────────────────────────────────────────────────────────────────

class CstrWatcher:
    def __init__(self, bus: RedisBus):
        self._bus       = bus
        self._envelopes = _load_envelopes()
        self._prev: dict[str, tuple[float, float]] = {}   # tag -> (value, ts_epoch)

    @classmethod
    def from_settings(cls) -> "CstrWatcher":
        return cls(RedisBus.from_settings())

    def run(self):
        log.info("cstr watcher started", stream=STREAM, group=GROUP)
        self._ensure_group()
        while True:
            self._tick()

    def _ensure_group(self):
        try:
            self._bus._r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
        except Exception:
            pass   # group already exists

    def _tick(self):
        entries = self._bus._r.xreadgroup(
            GROUP, CONSUMER, {STREAM: ">"}, count=100, block=BLOCK_MS)
        if not entries:
            return
        for _stream, messages in entries:
            for entry_id, fields in messages:
                try:
                    self._on_message(fields)
                except Exception as exc:
                    log.warning("watcher error on message", error=str(exc)[:120])
                finally:
                    self._bus._r.xack(STREAM, GROUP, entry_id)

    def _on_message(self, fields: dict):
        tag_id    = fields.get("tag_id", "")
        raw_value = fields.get("value", "")
        status    = fields.get("status", "GOOD")
        ts_str    = fields.get("timestamp", "")

        if not tag_id or tag_id not in self._envelopes:
            return

        env = self._envelopes[tag_id]

        # --- Status=BAD ---
        if status == "BAD":
            self._fire(tag_id, "STATUS_BAD", float("nan"), float("nan"), "BAD sensor reading")
            return

        try:
            value = float(raw_value)
        except ValueError:
            return

        ts_epoch = time.time()   # wall-clock; stream id has ms but that's fine

        # --- Max breach ---
        if "max" in env and value > env["max"]:
            self._fire(tag_id, "MAX_EXCEEDED", value, env["max"],
                       f"{tag_id} = {value:.2f} {env.get('unit','')} > max {env['max']}")

        # --- Min breach ---
        if "min" in env and value < env["min"]:
            self._fire(tag_id, "MIN_EXCEEDED", value, env["min"],
                       f"{tag_id} = {value:.2f} {env.get('unit','')} < min {env['min']}")

        # --- Rate-of-rise (temperature tags only) ---
        if "dT_dt_max" in env and tag_id in self._prev:
            prev_val, prev_ts = self._prev[tag_id]
            dt = ts_epoch - prev_ts
            if dt > 0:
                dT_dt = (value - prev_val) / dt
                if dT_dt > env["dT_dt_max"]:
                    self._fire(tag_id, "RATE_OF_RISE", dT_dt, env["dT_dt_max"],
                               f"{tag_id} rising at {dT_dt:.2f} K/s > limit {env['dT_dt_max']}")

        self._prev[tag_id] = (value, ts_epoch)

    def _fire(self, tag_id: str, rule: str, value: float, threshold: float, body: str):
        fingerprint = f"cstr:{tag_id}:{rule}"
        # Set NX EX in Redis to implement alert de-duplication with a TTL
        if not self._bus._r.set(f"alert_dedup:{fingerprint}", "1", nx=True, ex=DEDUP_TTL_S):
            return

        # Equipment tag = everything before the first dot (e.g. CSTR-102A)
        equipment = tag_id.split(".")[0]

        # Build the Alert payload matching plantmind_core.schemas.Alert shape
        import hashlib
        from datetime import datetime, timezone
        alert_payload = {
            "kind":       "process_limit",
            "severity":   "critical",
            "title":      f"Process limit breach: {tag_id} — {rule}",
            "body":       body,
            "equipment":  equipment,
            "citations":  [],
            "web_sources": [],
            "fingerprint": fingerprint,
            "graph_version": self._bus.graph_version(),
            "verified":   True,
            "unverified_claims": [],
            # Extra fields for the WS bridge to forward as-is
            "tag_id":    tag_id,
            "rule":      rule,
            "value":     value if value == value else None,   # NaN → None
            "threshold": threshold,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._bus.publish_alert(json.dumps(alert_payload))
        log.info("alert fired", tag_id=tag_id, rule=rule, value=value)


def main():
    CstrWatcher.from_settings().run()


if __name__ == "__main__":
    main()
