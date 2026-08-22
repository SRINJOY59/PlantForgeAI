"""Take aioice's mDNS resolver out of the ICE path.

Browsers anonymise their host candidates as `<uuid>.local` and publish them
over multicast DNS on their own LAN. A bot in a GKE pod is not on that LAN and
never will be, so those candidates are unresolvable here by construction - the
connection has to be made on the server-reflexive pair regardless.

aioice still stands up a shared, reference-counted mDNS listener the moment one
of those candidates arrives, and multicast does not work inside the pod. The
damage is not the failed lookup, which aioice handles: it is the teardown.
aiortc's setRemoteDescription routinely stops the ICE transports it did not end
up using, that path calls unref_mdns_protocol, and closing the protocol awaits
a future that never resolves - surfacing as CancelledError out of
setRemoteDescription. Every POST /api/offer answered 500 and voice could not
negotiate at all.

So the resolver is replaced with a stub that resolves nothing and closes
cleanly. aioice already treats an unresolved mDNS candidate as one to log and
skip, which is the correct outcome for this deployment anyway.
"""

from aioice import ice

from plantmind_core.telemetry import get_logger

log = get_logger("interview.voice.no_mdns")


class _NoMDnsProtocol:
    """Stands in for aioice's MDnsProtocol: resolves nothing, closes cleanly."""

    async def resolve(self, hostname, timeout=1.0):
        return None

    async def close(self):
        return None


_STUB = _NoMDnsProtocol()


async def _get_or_create_mdns_protocol(subscriber):
    return _STUB


async def _unref_mdns_protocol(subscriber):
    return None


def install() -> None:
    """Idempotent, so it is safe to call on every negotiation."""
    if getattr(ice, "_plantmind_mdns_disabled", False):
        return
    ice.get_or_create_mdns_protocol = _get_or_create_mdns_protocol
    ice.unref_mdns_protocol = _unref_mdns_protocol
    ice._plantmind_mdns_disabled = True
    log.info("aioice mDNS resolution disabled - .local candidates are skipped")
