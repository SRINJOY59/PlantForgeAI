"""Slack's return path into the gateway.

Everything else the gateway serves is authenticated by a Supabase JWT. These
routes cannot be: the caller is Slack, or a browser Slack just opened, and
neither has ever seen our auth. So the proof of authority travels in the
request itself, and there are two shapes of it:

  * POST /slack/interactions — a Block Kit button was tapped. Slack signs the
    raw body with the app's signing secret, and verify_slack_request() is the
    only thing between this endpoint and anyone on the internet who knows the
    URL. No signing secret configured means every call is refused.

  * GET /slack/approve then POST /slack/approve — a signed link was clicked.
    The token carries the draft, the decision and an expiry under an HMAC.

That link is split across two methods deliberately, and it is the one
non-obvious thing in this file. Slack (and Outlook, and every link-preview
bot in the chain) fetches URLs that appear in messages in order to unfurl
them. A GET that approved a work order would therefore approve it the instant
the message was POSTED, with no human involved at all - the crew would be
dispatched before anyone read the request. So the GET only renders a
confirmation page, and the POST behind its button is what actually decides.
A prefetcher does not press buttons.

These routes are registered WITHOUT the protected dependency in main.py. That
is load-bearing, not an oversight, and the verification above is what pays for
it.
"""

import json
import urllib.parse

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse

from plantmind_core.notify import (ApprovalTokenError, verify_approval,
                                   verify_slack_request)
from plantmind_core.telemetry import get_logger

from gateway.deps import get_service

log = get_logger("routes.slack")

router = APIRouter()

# The gateway's default CSP is default-src 'none', which is right for a JSON
# API and wrong for the only two HTML pages it serves - it would strip the
# stylesheet off them. Relaxed to exactly what these pages use: their own
# inline style block, and nothing else. Still no scripts, no external loads.
_PAGE_CSP = ("default-src 'none'; style-src 'unsafe-inline'; "
             "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")


def _page(title: str, message: str, *, status: int = 200,
          form_token: str = "", decision: str = "") -> HTMLResponse:
    """One of the two pages this file serves: a confirmation, or a result.

    Passing form_token turns it into the confirmation page - the button in it
    is what carries the decision through to the POST below.
    """
    accent = {"approved": "#16a34a", "rejected": "#dc2626"}.get(decision, "#38bdf8")
    action = ""
    if form_token:
        verb = "Approve this work order" if decision == "approved" else "Reject this work order"
        action = (
            '<form method="post" action="/slack/approve">'
            f'<input type="hidden" name="token" value="{_esc(form_token)}">'
            f'<button type="submit">{_esc(verb)}</button></form>'
            '<p class="fine">Nothing has been recorded yet. This step exists '
            'because chat clients open links automatically to preview them.</p>')

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{_esc(title)}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh; margin: 0; background: #0f172a; color: #e2e8f0; }}
  .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 16px;
    padding: 2.5rem; max-width: 26rem; text-align: center;
    box-shadow: 0 4px 24px rgba(0,0,0,.4); }}
  h1 {{ font-size: 1.25rem; margin: 0 0 .75rem; color: {accent}; }}
  p {{ color: #94a3b8; line-height: 1.6; margin: 0; }}
  button {{ margin-top: 1.5rem; width: 100%; padding: .75rem 1rem;
    font: inherit; font-weight: 600; color: #0f172a; background: {accent};
    border: 0; border-radius: 10px; cursor: pointer; }}
  .fine {{ margin-top: 1rem; font-size: .75rem; color: #64748b; }}
</style></head>
<body><div class="card"><h1>{_esc(title)}</h1><p>{_esc(message)}</p>
{action}</div></body></html>"""
    return HTMLResponse(html, status_code=status,
                        headers={"Content-Security-Policy": _PAGE_CSP})


def _esc(text: str) -> str:
    """Nothing rendered here is trusted input, but a draft id or an error
    string ending up between tags is not worth the argument."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ---------------------------------------------------------------- signed links
@router.get("/slack/approve")
async def confirm_via_link(token: str = ""):
    """Render what this link would do. Deliberately changes nothing.

    The token is still verified here so an expired or tampered link says so
    now, rather than after someone has committed to pressing the button.
    """
    try:
        draft_id, decision = verify_approval(token)
    except ApprovalTokenError as e:
        return _page("Link not valid", str(e), status=403)

    svc = get_service()
    record = svc.work_order_schedule(draft_id)
    if record is None:
        return _page("Nothing to decide",
                     "This work order has no schedule awaiting approval.",
                     status=404)
    if record.get("status") != "pending_approval":
        return _page("Already decided",
                     f"This work order was already {record.get('status')}"
                     f" by {record.get('decided_by') or 'someone'}.")

    verb = "approve" if decision == "approved" else "reject"
    window = record.get("window_start") or "an unspecified time"
    return _page(
        f"Confirm: {verb} this work order",
        f"Requested by {record.get('requested_by') or 'unknown'}, "
        f"scheduled to start {window}.",
        form_token=token, decision=decision)


@router.post("/slack/approve")
async def approve_via_link(token: str = Form("")):
    """The decision itself. Reached only by pressing the button above."""
    try:
        draft_id, decision = verify_approval(token)
    except ApprovalTokenError as e:
        return _page("Link not valid", str(e), status=403)

    svc = get_service()
    record = await svc.handle_schedule_decision(
        draft_id, decision, who="approved via Slack link", channel="link")
    if record is None:
        return _page("Already decided",
                     "This work order was approved or rejected already.")

    if decision != "approved":
        return _page("Work order rejected",
                     "No crew has been notified. The engineer can propose a "
                     "new schedule.", decision="rejected")
    if record.get("dispatch_error"):
        return _page("Approved, but not delivered",
                     f"The approval is recorded. Sending it to the crew "
                     f"failed: {record['dispatch_error']}. The engineer can "
                     f"retry from the console.", decision="approved")
    sent = len(record.get("dispatched_to") or [])
    return _page("Work order approved",
                 f"Sent to {sent} worker(s), each in their own language.",
                 decision="approved")


# --------------------------------------------------------- Block Kit buttons
@router.post("/slack/interactions")
async def slack_interactions(request: Request):
    """Slack posts here when a Block Kit button is tapped.

    The body is form-encoded with a single 'payload' key holding JSON. Slack
    signs the RAW body, so it is verified before anything is parsed out of it -
    parsing first would mean acting on attacker-shaped data to decide whether
    to trust the attacker.
    """
    body = await request.body()
    if not verify_slack_request(body,
                                request.headers.get("X-Slack-Request-Timestamp", ""),
                                request.headers.get("X-Slack-Signature", "")):
        log.warning("slack interaction failed signature verification")
        return Response(status_code=403)

    try:
        form = urllib.parse.parse_qs(body.decode())
        payload = json.loads(form.get("payload", ["{}"])[0])
    except Exception:
        return Response(status_code=400)

    actions = payload.get("actions") or []
    if not actions:
        return Response(status_code=200)

    action = actions[0]
    decision = {"work_order_approve": "approved",
                "work_order_reject": "rejected"}.get(action.get("action_id", ""))
    if decision is None:
        return Response(status_code=200)   # some other app's button

    draft_id = action.get("value", "")
    user = payload.get("user") or {}
    who = user.get("username") or user.get("name") or user.get("id") or "slack user"

    svc = get_service()
    record = await svc.handle_schedule_decision(draft_id, decision, who=who,
                                                channel="button")
    if record is None:
        return _ephemeral("This work order was already decided.")

    if decision != "approved":
        return _in_channel(f"Work order `{draft_id}` rejected by {who}. "
                           f"No crew notified.")
    if record.get("dispatch_error"):
        return _in_channel(f"Work order `{draft_id}` approved by {who}, but "
                           f"delivery to the crew failed: "
                           f"{record['dispatch_error']}")
    sent = len(record.get("dispatched_to") or [])
    return _in_channel(f"Work order `{draft_id}` approved by {who} and sent to "
                       f"{sent} worker(s) in their own languages.")


def _ephemeral(text: str) -> Response:
    """Seen only by whoever tapped - a duplicate press is their problem to
    understand, not something to announce to the channel."""
    return Response(content=json.dumps({"response_type": "ephemeral",
                                        "text": text}),
                    media_type="application/json")


def _in_channel(text: str) -> Response:
    """Everyone who saw the request should see the answer."""
    return Response(content=json.dumps({"response_type": "in_channel",
                                        "text": text}),
                    media_type="application/json")
