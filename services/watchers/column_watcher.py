"""Column threshold watcher — deterministic checks, no LLM.

Consumer group 'column-watchers' on plant:telemetry.
Monitors:
  - COLUMN-1.DISTILLATE.x (min 0.90)
  - COLUMN-1.BOTTOMS.x (max 0.08)
  - COLUMN-1.REBOILER.T (max 365.0, min 310.0)
  - COLUMN-1.FLOODING (max 1.20)

On breach: publishes to alerts:critical with kind="process_limit".
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Bootstrap sys.path for plantmind_core imports
_repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo / "libs" / "core"))

from plantmind_core.bus import RedisBus
from plantmind_core.telemetry import get_logger

log = get_logger("watchers.column")

STREAM       = "plant:telemetry"
ALERT_STREAM = "alerts:critical"
GROUP        = "column-watchers"
CONSUMER     = "column-watcher-1"
BLOCK_MS     = 10_000
DEDUP_TTL_S  = 60

_ENVELOPE_PATH = Path(__file__).resolve().parents[2] / "config" / "cstr_envelopes.json"


def _load_envelopes() -> dict:
    with open(_ENVELOPE_PATH) as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


class ColumnWatcher:
    def __init__(self, bus: RedisBus):
        self._bus       = bus
        self._envelopes = _load_envelopes()

    @classmethod
    def from_settings(cls) -> "ColumnWatcher":
        return cls(RedisBus.from_settings())

    def run(self):
        log.info("column watcher started", stream=STREAM, group=GROUP)
        self._ensure_group()
        while True:
            self._tick()

    def _ensure_group(self):
        try:
            self._bus._r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
        except Exception:
            pass

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
                    log.warning("column watcher error on message", error=str(exc)[:120])
                finally:
                    self._bus._r.xack(STREAM, GROUP, entry_id)

    def _on_message(self, fields: dict):
        tag_id    = fields.get("tag_id", "")
        raw_value = fields.get("value", "")
        status    = fields.get("status", "GOOD")

        if not tag_id or tag_id not in self._envelopes:
            return

        env = self._envelopes[tag_id]

        if status == "BAD":
            self._fire(tag_id, "STATUS_BAD", float("nan"), float("nan"), "BAD column sensor reading")
            return

        try:
            value = float(raw_value)
        except ValueError:
            return

        # Max check
        if "max" in env and value > env["max"]:
            self._fire(tag_id, "MAX_EXCEEDED", value, env["max"],
                       f"{tag_id} = {value:.4f} {env.get('unit','')} > max limit {env['max']}")

        # Min check
        if "min" in env and value < env["min"]:
            self._fire(tag_id, "MIN_EXCEEDED", value, env["min"],
                       f"{tag_id} = {value:.4f} {env.get('unit','')} < min limit {env['min']}")

    def _fire(self, tag_id: str, rule: str, value: float, threshold: float, body: str):
        fingerprint = f"column:{tag_id}:{rule}"
        # Set NX EX in Redis to implement alert de-duplication with a TTL
        if not self._bus._r.set(f"alert_dedup:{fingerprint}", "1", nx=True, ex=DEDUP_TTL_S):
            return

        # Equipment tag (everything before the first dot e.g. COLUMN-1)
        equipment = tag_id.split(".")[0]

        from datetime import datetime, timezone
        alert_payload = {
            "kind":       "process_limit",
            "severity":   "critical",
            "title":      f"Column process breach: {tag_id} — {rule}",
            "body":       body,
            "equipment":  equipment,
            "citations":  [],
            "web_sources": [],
            "fingerprint": fingerprint,
            "graph_version": self._bus.graph_version(),
            "verified":   True,
            "unverified_claims": [],
            # For ws bridge:
            "tag_id":    tag_id,
            "rule":      rule,
            "value":     value if value == value else None,
            "threshold": threshold,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._bus.publish_alert(json.dumps(alert_payload))
        log.info("column alert fired", tag_id=tag_id, rule=rule, value=value)


def main():
    ColumnWatcher.from_settings().run()


if __name__ == "__main__":
    main()
