"""SmallWebRTC signaling: the offer/answer exchange and trickle-ICE handling
that stand up a browser<->bot audio connection. Separated from bot.py because
this is transport plumbing - it knows nothing about the interview - while bot.py
is the pipeline that runs once a connection exists.

Instantiated per request around the shared connection map (which lives on
app.state as a plain dict, so importing this module - and pipecat - stays lazy,
off the no-voice startup path)."""

from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

ICE_SERVERS = ["stun:stun.l.google.com:19302"]


class WebRTCSignaler:
    """One signaling surface over the shared {pc_id: connection} map."""

    def __init__(self, conns: dict):
        self._conns = conns

    async def negotiate(self, body: dict):
        """One SmallWebRTC signaling exchange. Returns (answer, conn, is_new)."""
        pc_id = body.get("pc_id")
        if pc_id and pc_id in self._conns:
            conn = self._conns[pc_id]
            await conn.renegotiate(sdp=body["sdp"], type=body["type"],
                                   restart_pc=body.get("restart_pc", False))
            is_new = False
        else:
            conn = SmallWebRTCConnection(ice_servers=ICE_SERVERS)
            await conn.initialize(sdp=body["sdp"], type=body["type"])
            conns = self._conns

            @conn.event_handler("closed")
            async def _closed(c):
                conns.pop(c.pc_id, None)

            is_new = True
        answer = conn.get_answer()
        self._conns[answer["pc_id"]] = conn
        return answer, conn, is_new

    def get(self, pc_id: str):
        return self._conns.get(pc_id)

    @staticmethod
    async def add_candidates(conn: SmallWebRTCConnection, candidates: list):
        """The client SDK gathers ICE candidates asynchronously and PATCHes
        them in after the initial offer (trickle ICE) rather than waiting for
        gathering to complete - this is its default behaviour, not an edge
        case. Without adding them, the connection is limited to whatever
        candidates existed at offer time, which can fail to connect at all on
        less trivial networks (host-only worked in same-machine dev testing,
        which is why this was easy to miss)."""
        from aiortc.sdp import candidate_from_sdp

        for c in candidates:
            raw = c.get("candidate") or ""
            if not raw:
                continue
            # candidate_from_sdp parses the "candidate:..." attribute value only
            parsed = candidate_from_sdp(raw.removeprefix("candidate:"))
            parsed.sdpMid = c.get("sdp_mid")
            parsed.sdpMLineIndex = c.get("sdp_mline_index")
            await conn.add_ice_candidate(parsed)
