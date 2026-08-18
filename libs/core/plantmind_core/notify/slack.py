"""Slack notifications, kept deliberately narrow.

The failure mode of plant alerting is a channel so noisy people mute it - at
which point it is worse than nothing. So this sends only what a human needs to
see NOW and cannot already see elsewhere: right now that is CRITICAL process
alarms, deduped per fault episode. The design leaves room for the next triggers
(a confirmed-fault diagnosis, an RCA verdict, pipeline-health failures) without
widening the firehose.

Three principles the callers rely on:

  * Off by default. No webhook, no send - and a Slack outage never breaks the
    caller: every failure is swallowed and logged, because a plant alarm must
    reach redis whether or not Slack is reachable.
  * Severity-gated. Below slack_min_severity, nothing is sent.
  * Deduped. The caller passes a fingerprint; the same fingerprint is not
    re-sent within slack_dedup_ttl_s. Dedup needs a shared store to work across
    processes, so a redis client is passed in; without one, dedup is skipped
    (single-sender setups still behave, they just can't coordinate).

Posting is synchronous (requests) because the one caller today, the TEP watcher,
is a synchronous loop. An async variant can be added when an async caller needs
it.
"""

from __future__ import annotations

import requests

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger

log = get_logger("notify.slack")

# Least -> most severe. A message is sent when its severity ranks at or above
# the configured floor.
SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}

_POST_TIMEOUT_S = 5


class SlackNotifier:
    def __init__(self, webhook_url: str, enabled: bool, min_severity: str,
                 dedup_ttl_s: int, redis_client=None):
        self._url = webhook_url
        self._enabled = bool(enabled and webhook_url)
        self._min_rank = SEVERITY_RANK.get(min_severity, SEVERITY_RANK["critical"])
        self._dedup_ttl_s = dedup_ttl_s
        self._redis = redis_client

    @classmethod
    def from_settings(cls, redis_client=None) -> "SlackNotifier":
        s = get_settings()
        webhook_url = getattr(s, "slack_webhook_url", "")
        # Auto-enable if webhook URL is configured or explicitly enabled
        enabled = bool(getattr(s, "slack_enabled", False) or webhook_url)
        return cls(
            webhook_url=webhook_url,
            enabled=enabled,
            min_severity=getattr(s, "slack_min_severity", "critical"),
            dedup_ttl_s=getattr(s, "slack_dedup_ttl_s", 1800),
            redis_client=redis_client,
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _passes_severity(self, severity: str) -> bool:
        return SEVERITY_RANK.get((severity or "").lower(), 0) >= self._min_rank

    def _claim(self, fingerprint: str) -> bool:
        """True if this fingerprint has not been sent in the dedup window.

        Uses SET NX EX so the first sender wins and later duplicates are dropped.
        With no redis client we cannot coordinate, so we allow the send - it is
        better to risk a duplicate than to silently swallow a real alert."""
        if not fingerprint or self._redis is None:
            return True
        try:
            return bool(self._redis.set(f"slack:sent:{fingerprint}", "1",
                                        nx=True, ex=self._dedup_ttl_s))
        except Exception as e:
            log.warning("slack dedup check failed; sending anyway", error=str(e))
            return True

    def post_alarm(self, payload: dict) -> bool:
        """Send a process alarm if it clears the bar: enabled, severe enough,
        and not a duplicate. Returns whether a message was actually sent."""
        if not self._enabled:
            return False
        severity = payload.get("severity", "warning")
        if not self._passes_severity(severity):
            return False
        if not self._claim(payload.get("fingerprint", "")):
            return False
        return self._send(self._alarm_blocks(payload),
                          fallback=payload.get("message", "Process alarm"))

    def post_text(self, text: str, *, fingerprint: str = "") -> bool:
        """A plain text message - for pipeline-health notices and the like."""
        if not self._enabled or not self._claim(fingerprint):
            return False
        return self._send(None, fallback=text)

    def post_compliance_alert(self, item: dict) -> bool:
        """Send an alert for an overdue statutory inspection or standard violation."""
        if not self._enabled:
            return False
        equip = item.get("equipment", "Unknown")
        std = item.get("standard", "Standard")
        itype = item.get("inspection_type", "Inspection")
        due = item.get("next_due", "Past Due")
        status = item.get("status", "overdue").upper()
        
        header = f"⚠️ STATUTORY COMPLIANCE ALERT — {equip} ({std})"
        fields = [
            {"type": "mrkdwn", "text": f"*Equipment:* `{equip}`"},
            {"type": "mrkdwn", "text": f"*Standard:* *{std}*"},
            {"type": "mrkdwn", "text": f"*Inspection Type:* {itype}"},
            {"type": "mrkdwn", "text": f"*Status:* *{status}* (Due: {due})"},
        ]
        if item.get("last_inspection"):
            fields.append({"type": "mrkdwn", "text": f"*Last Inspection:* {item['last_inspection']}"})
            
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": header[:150]}},
            {"type": "section", "fields": fields[:10]},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Statutory requirement logged in PlantForge Knowledge Graph. Schedule work order immediately."}]}
        ]
        return self._send(blocks, fallback=f"Statutory Compliance Alert: {equip} - {std} is {status}")

    def post_test(self, user_name: str = "Engineer") -> bool:
        """Send an interactive test notification verifying Slack integration."""
        if not self._enabled:
            return False
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "✅ PlantForge AI — Slack Notifications Connected"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Triggered By:* {user_name}"},
                {"type": "mrkdwn", "text": "*Status:* Connected & Active"},
                {"type": "mrkdwn", "text": "*Active Channels:* Process Alarms, Compliance & Standards"},
                {"type": "mrkdwn", "text": "*Severity Filter:* CRITICAL & WARNING"},
            ]},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": "Live alerts from PlantForge TEP simulator, AI RCA investigator, and statutory compliance monitor will appear in this channel."}]}
        ]
        return self._send(blocks, fallback="✅ PlantForge AI — Slack Notifications Connected Successfully")

    # ------------------------------------------------------------- rendering
    @staticmethod
    def _alarm_blocks(p: dict) -> list:
        sev = str(p.get("severity", "warning")).upper()
        icon = "🔴" if sev == "CRITICAL" else "🟠"
        tag = p.get("tag_id", "?")
        level = p.get("level", "?")
        header = f"{icon} {sev} process alarm — {tag} ({level})"
        fields = []
        for label, key in (("Unit", "unit"), ("Value", "value"),
                           ("Limit", "limit"), ("Setpoint", "setpoint")):
            val = p.get(key)
            if val not in (None, ""):
                fields.append({"type": "mrkdwn", "text": f"*{label}:* {val}"})
        blocks = [{"type": "header",
                   "text": {"type": "plain_text", "text": header[:150]}}]
        if fields:
            blocks.append({"type": "section", "fields": fields[:10]})
        msg = p.get("message")
        if msg:
            blocks.append({"type": "context",
                           "elements": [{"type": "mrkdwn", "text": msg[:300]}]})
        return blocks

    def _send(self, blocks: list | None, fallback: str) -> bool:
        body = {"text": fallback}
        if blocks:
            body["blocks"] = blocks
        try:
            r = requests.post(self._url, json=body, timeout=_POST_TIMEOUT_S)
            if r.status_code >= 300:
                log.warning("slack post non-2xx", status=r.status_code,
                            body=r.text[:200])
                return False
            return True
        except Exception as e:
            # A plant alarm must reach redis whether or not Slack is up - never
            # let a webhook failure propagate into the caller's loop.
            log.warning("slack post failed", error=str(e))
            return False
