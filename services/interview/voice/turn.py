"""ICE server config for the WebRTC leg, including TURN.

Behind a cloud L7 load balancer the browser and the bot cannot reach each other
directly - their host/srflx candidates are private or NATed - so media needs a
TURN relay both peers can reach. This builds the ICE server list (STUN + TURN)
and mints the TURN credential.

TURN auth uses coturn's time-limited REST scheme (`use-auth-secret`): the
username is an expiry timestamp and the credential is an HMAC of it under a
shared secret. No static passwords, and a leaked credential dies in an hour.
Server and client share only the secret's *output* per session, never the
secret itself - the backend mints, the browser receives via /api/turn.

Config comes from the environment (set on the interview deployment):
  TURN_URL     - e.g. "turn:turn.example.com:3478" (comma-separated for several)
  TURN_SECRET  - the coturn static-auth-secret
  STUN_URL     - default a public Google STUN; only helps direct paths
With TURN_URL/TURN_SECRET unset the list is STUN-only and voice works only where
a direct path exists (local dev) - exactly today's behaviour.
"""

import base64
import hashlib
import hmac
import os
import time

_DEFAULT_STUN = "stun:stun.l.google.com:19302"
_TTL_S = 3600


def _turn_credential(secret: str, ttl: int = _TTL_S) -> tuple[str, str]:
    """(username, credential) for coturn use-auth-secret."""
    username = f"{int(time.time()) + ttl}:plantmind"
    digest = hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
    return username, base64.b64encode(digest).decode()


def ice_config() -> list[dict]:
    """The RTCIceServer list, as plain dicts ({urls, username?, credential?}) -
    the shape both aiortc and the browser accept. Fresh TURN credentials each
    call, since they expire."""
    servers: list[dict] = []
    stun = os.environ.get("STUN_URL", _DEFAULT_STUN)
    if stun:
        servers.append({"urls": stun})

    turn_url = os.environ.get("TURN_URL", "").strip()
    turn_secret = os.environ.get("TURN_SECRET", "").strip()
    if turn_url and turn_secret:
        username, credential = _turn_credential(turn_secret)
        urls = [u.strip() for u in turn_url.split(",") if u.strip()]
        servers.append({"urls": urls, "username": username,
                        "credential": credential})
    return servers


def pipecat_ice_servers():
    """The same list, as whatever pipecat's SmallWebRTCConnection wants. Recent
    pipecat takes IceServer objects; older takes URL strings. Prefer IceServer
    so TURN credentials survive; fall back to URLs (STUN-only) if the type moved.
    """
    cfg = ice_config()
    try:
        from pipecat.transports.smallwebrtc.connection import IceServer
        out = []
        for s in cfg:
            urls = s["urls"]
            url = urls[0] if isinstance(urls, list) else urls
            out.append(IceServer(urls=url, username=s.get("username"),
                                 credential=s.get("credential")))
        return out
    except Exception:
        # last resort: URL strings only (loses TURN auth). Logged by the caller.
        flat = []
        for s in cfg:
            urls = s["urls"]
            flat.extend(urls if isinstance(urls, list) else [urls])
        return flat
