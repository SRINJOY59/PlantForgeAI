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


def _clip(text, limit: int) -> str:
    """Slack truncates a long block server-side and the tail is silently lost,
    so cut it here where we can say so."""
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _format_window(start, end) -> str:
    """The proposed slot, as written by the engineer. Rendered verbatim rather
    than reformatted into a timezone: the approver and the crew are standing in
    the same plant, and a helpfully converted timestamp is how a night shift
    gets sent in at the wrong hour."""
    start = (start or "").replace("T", " ")
    end = (end or "").replace("T", " ")
    if start and end:
        return f"{start} → {end}"
    return start or end or "_not specified_"


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

    def post_work_order_approval(self, draft: dict, schedule: dict) -> bool:
        """Ask Slack to authorise a scheduled work order.

        The one message in here that is not a notification. Everything else
        this class sends is telling somebody what happened; this is asking, and
        nothing moves until it is answered - so it is exempt from the severity
        floor and from dedup. A re-proposed schedule after a rejection is a
        genuinely new question, and silently swallowing it as a duplicate would
        strand the engineer waiting on an answer that was never asked for.

        Both return paths ride on the same message. The buttons work only where
        a Slack app is installed and the gateway is reachable; the links below
        them need nothing but this webhook. Whichever the workspace supports is
        the one that gets used - and a reader can see the ID they are approving
        either way.
        """
        if not self._enabled:
            return False

        equip = draft.get("equipment") or "Unknown asset"
        priority = str(draft.get("priority") or "medium").upper()
        order_type = draft.get("order_type") or "PM01"
        draft_id = schedule.get("draft_id", "")
        window = _format_window(schedule.get("window_start"),
                               schedule.get("window_end"))
        crew = schedule.get("crew_names") or []

        fields = [
            {"type": "mrkdwn", "text": f"*Equipment:* `{equip}`"},
            {"type": "mrkdwn", "text": f"*Priority:* *{priority}*"},
            {"type": "mrkdwn", "text": f"*Order type:* {order_type}"},
            {"type": "mrkdwn", "text": f"*Window:* {window}"},
            {"type": "mrkdwn", "text": f"*Requested by:* {schedule.get('requested_by', 'unknown')}"},
            {"type": "mrkdwn",
             "text": f"*Crew:* {', '.join(crew) if crew else '_not yet assigned_'}"},
        ]

        blocks = [
            {"type": "header", "text": {"type": "plain_text",
                                        "text": f"🛠️ Approval needed — schedule work on {equip}"[:150]}},
            {"type": "section", "fields": fields[:10]},
        ]

        fix = _clip(draft.get("recommended_fix"), 600)
        if fix:
            blocks.append({"type": "section",
                           "text": {"type": "mrkdwn", "text": f"*Recommended fix*\n{fix}"}})
        notes = _clip(schedule.get("notes"), 300)
        if notes:
            blocks.append({"type": "section",
                           "text": {"type": "mrkdwn", "text": f"*Engineer's note*\n{notes}"}})

        # The value carries the draft id because that is what the handler acts
        # on; the action_id carries the decision so a mis-wired button cannot
        # approve something by defaulting.
        blocks.append({"type": "actions", "block_id": f"wo_approval:{draft_id}",
                       "elements": [
                           {"type": "button", "action_id": "work_order_approve",
                            "style": "primary", "value": draft_id,
                            "text": {"type": "plain_text", "text": "Approve"}},
                           {"type": "button", "action_id": "work_order_reject",
                            "style": "danger", "value": draft_id,
                            "text": {"type": "plain_text", "text": "Reject"}},
                       ]})

        try:
            from plantmind_core.notify.approvals import approval_links
            links = approval_links(draft_id)
            blocks.append({"type": "context", "elements": [
                {"type": "mrkdwn",
                 "text": (f"Buttons not working? <{links['approved']}|Approve> · "
                          f"<{links['rejected']}|Reject>")}]})
        except Exception as e:
            # A missing link is a degraded message, not a failed one - the
            # buttons may well be the working path in this workspace.
            log.warning("could not build approval links", error=str(e))

        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn",
             "text": (f"Draft `{draft_id}` · no crew is notified until this is "
                      f"approved.")}]})

        return self._send(blocks,
                          fallback=f"Approval needed: schedule work on {equip} ({priority})")

    def post_work_order_dispatched(self, draft: dict, schedule: dict,
                                   recipients: list) -> bool:
        """Close the loop in the same channel that authorised it.

        Whoever approved this is entitled to see that it actually went out, and
        to whom - an approval whose consequence is invisible is one people stop
        reading carefully.
        """
        if not self._enabled:
            return False
        equip = draft.get("equipment") or "Unknown asset"
        who = ", ".join(f"{r.get('name')} ({r.get('lang', 'en')})"
                        for r in recipients) or "nobody"
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn",
             "text": (f"✅ *Work order dispatched* — `{equip}`\n"
                      f"Sent to {len(recipients)} worker(s): {who}")}},
            {"type": "context", "elements": [
                {"type": "mrkdwn",
                 "text": (f"Approved by {schedule.get('decided_by', 'unknown')} · "
                          f"window {_format_window(schedule.get('window_start'), schedule.get('window_end'))} · "
                          f"each worker received it in their own language.")}]},
        ]
        return self._send(blocks,
                          fallback=f"Work order dispatched: {equip} to {len(recipients)} worker(s)")

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
