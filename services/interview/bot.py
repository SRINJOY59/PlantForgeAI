"""The Pipecat voice pipeline: browser mic -> WebRTC -> Silero VAD ->
Deepgram STT -> LLM (OpenRouter, same models as the rest of PlantMind) ->
Deepgram/Cartesia/ElevenLabs TTS -> browser speaker. The interview brain
stays in SessionMemory/service.py; this file only wires it to audio.

Written against pipecat-ai 0.0.108 - symbol paths move between releases,
so the pin in infra/docker/requirements/interview.txt matters."""

import asyncio

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frameworks.rtvi import (RTVIConfig, RTVIObserver,
                                                RTVIProcessor)
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from plantmind_core.config import get_settings
from plantmind_core.llm import get_llm
from plantmind_core.telemetry import get_logger

from interview.config import InterviewConfig
from interview.memory import SessionMemory
from interview.service import (TOOL_DEFS, interviewer_system,
                               make_tool_handlers)

log = get_logger("interview.bot")

ICE_SERVERS = ["stun:stun.l.google.com:19302"]
BRAIN_INTERVAL_S = 20      # digest + prompt-refresh cadence
DIGEST_MIN_TURNS = 4
COMPACT_ABOVE = 60         # context messages before old turns are trimmed
KEEP_TAIL = 30
AUDIO_IN_RATE = 16000      # mic -> STT (Deepgram nova)
AUDIO_OUT_RATE = 24000     # TTS (Deepgram aura) -> speaker


async def add_trickled_candidates(conn: SmallWebRTCConnection, candidates: list):
    """The client SDK gathers ICE candidates asynchronously and PATCHes them
    in after the initial offer (trickle ICE) rather than waiting for
    gathering to complete - this is its default behaviour, not an edge
    case. Without adding them, the connection is limited to whatever
    candidates existed at offer time, which can fail to connect at all on
    less trivial networks (host-only worked in same-machine dev testing,
    which is why this was easy to miss)."""
    from aiortc import RTCIceCandidate
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


async def negotiate(body: dict, conns: dict):
    """One SmallWebRTC signaling exchange. Returns (answer, conn, is_new)."""
    pc_id = body.get("pc_id")
    if pc_id and pc_id in conns:
        conn = conns[pc_id]
        await conn.renegotiate(sdp=body["sdp"], type=body["type"],
                               restart_pc=body.get("restart_pc", False))
        is_new = False
    else:
        conn = SmallWebRTCConnection(ice_servers=ICE_SERVERS)
        await conn.initialize(sdp=body["sdp"], type=body["type"])

        @conn.event_handler("closed")
        async def _closed(c):
            conns.pop(c.pc_id, None)

        is_new = True
    answer = conn.get_answer()
    conns[answer["pc_id"]] = conn
    return answer, conn, is_new


def _make_tts(cfg: InterviewConfig):
    if cfg.tts_provider == "cartesia" and cfg.cartesia_api_key:
        try:
            from pipecat.services.cartesia.tts import CartesiaTTSService
            return CartesiaTTSService(api_key=cfg.cartesia_api_key)
        except ImportError:
            log.warning("cartesia extra not installed, using deepgram tts")
    if cfg.tts_provider == "elevenlabs" and cfg.elevenlabs_api_key:
        try:
            from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
            return ElevenLabsTTSService(api_key=cfg.elevenlabs_api_key)
        except ImportError:
            log.warning("elevenlabs extra not installed, using deepgram tts")
    return DeepgramTTSService(api_key=cfg.deepgram_api_key,
                              voice="aura-2-thalia-en",
                              sample_rate=AUDIO_OUT_RATE)


def _tools_schema() -> ToolsSchema:
    return ToolsSchema(standard_tools=[
        FunctionSchema(name=d["name"], description=d["description"],
                       properties=d["parameters"]["properties"],
                       required=d["parameters"].get("required", []))
        for d in TOOL_DEFS])


def _refresh_system(context: OpenAILLMContext, memory: SessionMemory):
    """Replace the system message in place - the INTERVIEW STATE inside it
    is the no-repeat guarantee, and appending instead would grow forever."""
    messages = context.get_messages()
    rest = [m for m in messages if m.get("role") != "system"]
    context.set_messages(
        [{"role": "system", "content": interviewer_system(memory)}] + rest)


def _compact(context: OpenAILLMContext):
    """Long call: trim old turns from the LLM window. Nothing is lost -
    facts live in SessionMemory and come back via the state block."""
    messages = context.get_messages()
    if len(messages) <= COMPACT_ABOVE:
        return
    system = [m for m in messages if m.get("role") == "system"][:1]
    tail = messages[-KEEP_TAIL:]
    # never start the tail on a dangling tool response
    while tail and tail[0].get("role") == "tool":
        tail = tail[1:]
    note = {"role": "system", "content":
            "(Earlier turns trimmed for length; everything learned so far "
            "is reflected in the INTERVIEW STATE block above.)"}
    context.set_messages(system + [note] + tail)


async def run_bot(conn: SmallWebRTCConnection, memory: SessionMemory,
                  cfg: InterviewConfig):
    """Owns one voice call. Blocks until the call ends; the caller
    (main._run_voice) finalizes the session afterwards."""
    settings = get_settings()

    transport = SmallWebRTCTransport(
        webrtc_connection=conn,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=AUDIO_IN_RATE,
            audio_out_sample_rate=AUDIO_OUT_RATE,
            vad_analyzer=SileroVADAnalyzer()))

    # Two Deepgram-connection gotchas in pipecat 0.0.108, both of which make
    # the STT websocket 400 in an endless retry loop (bot hears nothing, the
    # pipeline jams):
    #   1. sample_rate left unset can serialise as "None"/"0".
    #   2. the default language enum serialises to the literal "Language.EN"
    #      instead of "en" - an invalid Deepgram language code. addons are
    #      applied last in the query builder, so they override it with "en".
    stt = DeepgramSTTService(api_key=cfg.deepgram_api_key,
                             sample_rate=AUDIO_IN_RATE,
                             addons={"language": "en"})
    tts = _make_tts(cfg)
    llm = OpenAILLMService(api_key=settings.openrouter_api_key,
                           base_url=settings.openrouter_base_url,
                           model=cfg.llm_model)

    context = OpenAILLMContext(
        messages=[{"role": "system", "content": interviewer_system(memory)}],
        tools=_tools_schema())
    aggregator = llm.create_context_aggregator(context)

    handlers = make_tool_handlers(memory)

    def bind(name):
        async def handler(params):
            result = handlers[name](**(params.arguments or {}))
            await params.result_callback(result)
        return handler

    for tool_name in handlers:
        llm.register_function(tool_name, bind(tool_name))

    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))
    transcript = TranscriptProcessor()

    pipeline = Pipeline([
        transport.input(),
        rtvi,
        stt,
        transcript.user(),
        aggregator.user(),
        llm,
        tts,
        transport.output(),
        transcript.assistant(),
        aggregator.assistant(),
    ])
    task = PipelineTask(pipeline,
                        params=PipelineParams(allow_interruptions=True),
                        observers=[RTVIObserver(rtvi)])

    @transcript.event_handler("on_transcript_update")
    async def _on_transcript(processor, frame):
        for msg in frame.messages:
            memory.add_turn(msg.role, msg.content)

    @rtvi.event_handler("on_client_ready")
    async def _on_client_ready(rtvi_processor):
        await rtvi_processor.set_bot_ready()
        memory.status = "live"
        memory.save()
        # hand the context to the LLM so the bot greets first
        await task.queue_frames([aggregator.user().get_context_frame()])

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnect(transport_, client):
        log.info("client disconnected", session=memory.session_id)
        await task.cancel()

    async def brain():
        """Runs beside the call: digest new turns, refresh the prompt,
        trim the window, and speak the farewell when the interview ends."""
        farewell_sent = False
        while True:
            await asyncio.sleep(BRAIN_INTERVAL_S)
            try:
                if memory.status == "ending" and not farewell_sent:
                    farewell_sent = True
                    await task.queue_frames([
                        TTSSpeakFrame(
                            "Thank you, this has been genuinely valuable. "
                            "I am writing up your handover document now."),
                        EndFrame()])
                    return
                if memory.undigested_turns() >= DIGEST_MIN_TURNS:
                    if await memory.digest(get_llm()):
                        _refresh_system(context, memory)
                _compact(context)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.warning("brain loop error", session=memory.session_id,
                            error=str(e)[:200])

    brain_task = asyncio.create_task(brain())
    # no Unix signals on Windows - the API process owns ctrl-c handling
    runner = PipelineRunner(handle_sigint=False)
    log.info("voice call starting", session=memory.session_id,
             model=cfg.llm_model, tts=cfg.tts_provider)
    try:
        await runner.run(task)
    finally:
        brain_task.cancel()
        log.info("voice call ended", session=memory.session_id,
                 turns=len(memory.transcript))
