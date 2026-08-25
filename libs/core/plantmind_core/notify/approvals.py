"""Trusting what comes back from Slack.

Everywhere else in this codebase, "who is this" is answered by a Supabase JWT
the gateway verifies. Slack cannot carry one: the human approving a work order
is tapping a button in a chat client that knows nothing about our auth. So this
module is the substitute, and it has to be, because the thing on the other end
of these two paths is authority to send a crew into a plant.

Two paths, two different proofs, both landing on the same handler:

  * A Block Kit button posts to /slack/interactions. Slack signs every such
    request with the app's signing secret; verify_slack_request() is the
    standard v0 scheme, and it is the ONLY thing standing between that endpoint
    and anyone on the internet with the URL. No signing secret configured means
    the endpoint refuses - an unverifiable approval is not an approval.

  * A signed link carries its own proof in the URL, so it works with nothing
    but the Incoming Webhook that is already configured. The token binds the
    draft, the decision and an expiry together under an HMAC, which is what
    stops a recipient editing "reject" into "approve" in their address bar, or
    keeping a link alive to authorise next month's work.

Both comparisons use compare_digest. A timing-safe compare costs nothing and
the alternative is a real, published attack on exactly this shape of check.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger

log = get_logger("notify.approvals")

# Slack rejects its own replayed requests at five minutes; matching that keeps
# a captured request from being useful for longer against us than against them.
_MAX_SKEW_S = 300

_warned_derived = False


class ApprovalTokenError(ValueError):
    """The token did not verify. Deliberately one error for every reason -
    expired, tampered, malformed - because telling a caller which of those it
    was is telling an attacker how close they got."""


def _link_secret() -> bytes:
    """The HMAC key for approval links.

    Configured, or derived. Deriving is a compromise with eyes open: the
    gateway runs multiple uvicorn workers and a per-process random key would
    mean an approval link minted by worker 1 fails on worker 2, which looks
    exactly like tampering and would make the feature seem broken rather than
    unconfigured. Derivation is deterministic across workers and still not
    guessable without the other secrets - but it inherits their rotation, so
    production sets slack_approval_secret explicitly and says so out loud here.
    """
    global _warned_derived
    s = get_settings()
    configured = getattr(s, "slack_approval_secret", "")
    if configured:
        return configured.encode()
    if not _warned_derived:
        log.warning("slack_approval_secret unset - deriving approval link key "
                    "from other secrets; set it explicitly in production")
        _warned_derived = True
    material = "|".join(["plantmind-approval-v1",
                         getattr(s, "supabase_jwt_secret", ""),
                         getattr(s, "slack_webhook_url", ""),
                         getattr(s, "redis_url", "")])
    return hashlib.sha256(material.encode()).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def sign_approval(draft_id: str, decision: str, ttl_s: int | None = None) -> str:
    """A single-purpose approval token: this draft, this decision, until then.

    The decision is inside the signed payload rather than a separate query
    parameter for the obvious reason - a token that authorises "a decision on
    draft X" is a token that authorises approving it.
    """
    ttl = ttl_s if ttl_s is not None else getattr(
        get_settings(), "slack_approval_ttl_s", 86400)
    payload = f"{draft_id}|{decision}|{int(time.time()) + int(ttl)}"
    sig = hmac.new(_link_secret(), payload.encode(), hashlib.sha256).digest()
    return f"{_b64(payload.encode())}.{_b64(sig)}"


def verify_approval(token: str) -> tuple[str, str]:
    """Return (draft_id, decision) for a good token; raise otherwise.

    Signature first, expiry second. Reading the expiry out of an unverified
    payload and acting on it would mean trusting a field an attacker wrote.
    """
    try:
        encoded, _, sig_part = (token or "").partition(".")
        payload = _unb64(encoded)
        given = _unb64(sig_part)
    except Exception:
        raise ApprovalTokenError("malformed approval token")

    expected = hmac.new(_link_secret(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, given):
        raise ApprovalTokenError("approval token failed verification")

    try:
        draft_id, decision, expiry = payload.decode().split("|")
        expires_at = int(expiry)
    except (UnicodeDecodeError, ValueError):
        raise ApprovalTokenError("approval token failed verification")

    if time.time() > expires_at:
        raise ApprovalTokenError("approval link has expired")
    if decision not in ("approved", "rejected"):
        raise ApprovalTokenError("approval token failed verification")
    return draft_id, decision


def approval_links(draft_id: str) -> dict:
    """The approve/reject URLs to put on the Slack message."""
    base = getattr(get_settings(), "public_gateway_url",
                   "http://localhost:8000").rstrip("/")
    return {d: f"{base}/slack/approve?token={sign_approval(draft_id, d)}"
            for d in ("approved", "rejected")}


def verify_slack_request(body: bytes, timestamp: str, signature: str) -> bool:
    """Is this really Slack, and is it recent?

    Both halves matter. The signature alone would let a request captured off
    the wire be replayed indefinitely, and the timestamp is inside the signed
    base string precisely so it cannot be edited to keep an old body fresh.
    """
    secret = getattr(get_settings(), "slack_signing_secret", "")
    if not secret:
        log.warning("slack_signing_secret unset - refusing Slack interaction")
        return False
    try:
        if abs(time.time() - int(timestamp)) > _MAX_SKEW_S:
            log.warning("slack interaction outside timestamp window")
            return False
    except (TypeError, ValueError):
        return False
    basestring = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(secret.encode(), basestring,
                                hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")
