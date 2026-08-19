"""The Pipecat voice pipeline: browser mic -> WebRTC -> Silero VAD ->
Deepgram STT -> LLM (OpenRouter, same models as the rest of PlantMind) ->
Deepgram/Cartesia/ElevenLabs TTS -> browser speaker. The interview brain
stays in domain/ (memory, notetaker, interviewer); this class only wires it
to audio.

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
from interview.domain import Interviewer, Notetaker, SessionMemory

log = get_logger("interview.voice.bot")


def _build_llm(settings, cfg) -> OpenAILLMService:
    """The realtime interviewer LLM, pointed at the configured provider.

    On Vertex (the default for this deployment) it mints a fresh ADC token per
    session and talks to the Vertex OpenAI-compatible endpoint - the same
    provider the rest of PlantMind uses, so the interview stops depending on a
    separate OpenRouter balance. The token lasts about an hour, which covers an
    interview; a session running longer would need a reconnect. Falls back to
    OpenRouter when that is the configured provider (or Vertex has no ADC)."""
    provider = getattr(settings, "llm_provider", "openrouter")
    if provider == "vertex":
        try:
            import os
            import google.auth
            import google.auth.transport.requests
            project = (getattr(settings, "gcp_project", "")
                       or os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
            region = (getattr(settings, "vertex_region", "")
                      or os.environ.get("VERTEX_REGION", "us-central1"))
            creds, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"])
            creds.refresh(google.auth.transport.requests.Request())
            base_url = (f"https://{region}-aiplatform.googleapis.com/v1beta1"
                        f"/projects/{project}/locations/{region}"
                        f"/endpoints/openapi/")
            model = getattr(settings, "vertex_llm_mid", "google/gemini-2.5-flash")
            log.info("interview LLM on Vertex", model=model, region=region)
            return OpenAILLMService(api_key=creds.token, base_url=base_url,
                                    model=model)
        except Exception as e:
            log.warning("Vertex LLM setup failed; falling back to OpenRouter",
                        error=str(e)[:160])
    return OpenAILLMService(api_key=settings.openrouter_api_key,
                            base_url=settings.openrouter_base_url,
                            model=cfg.llm_model)

BRAIN_TICK_S = 3           # fast loop: pick up the background agenda promptly
BRAIN_INTERVAL_S = 20      # digest cadence
DIGEST_EVERY = BRAIN_INTERVAL_S // BRAIN_TICK_S   # ticks between digests
DIGEST_MIN_TURNS = 4
COMPACT_ABOVE = 60         # context messages before old turns are trimmed
KEEP_TAIL = 30
AUDIO_IN_RATE = 16000      # mic -> STT (Deepgram nova)
AUDIO_OUT_RATE = 24000     # TTS (Deepgram aura) -> speaker


class VoiceBot:
    """Owns one voice call: builds the Pipecat pipeline for a session's memory
    and runs it until the call ends."""

    def __init__(self, memory: SessionMemory, cfg: InterviewConfig):
        self._memory = memory
        self._cfg = cfg
        self._interviewer = Interviewer(memory)
        self._notetaker = Notetaker(get_llm())

    async def run(self, conn: SmallWebRTCConnection):
        """Blocks until the call ends; the caller finalizes the session after."""
        memory, cfg = self._memory, self._cfg
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
        tts = self._make_tts(cfg)
        llm = _build_llm(settings, cfg)

        context = OpenAILLMContext(
            messages=[
                {"role": "system",
                 "content": self._interviewer.system_prompt()},
                {"role": "user",
                 "content": "Please introduce yourself and start the interview."}
            ],
            tools=self._tools_schema())
        aggregator = llm.create_context_aggregator(context)

        handlers = self._interviewer.tool_handlers()

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

        brain_task = asyncio.create_task(self._brain(task, context))
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

    async def _brain(self, task, context: OpenAILLMContext):
        """Runs beside the call on a fast tick: pick up the background agenda
        the moment it lands, speak the farewell when the interview ends, and -
        on the slower cadence - digest new turns and trim the window."""
        memory = self._memory
        farewell_sent = False
        agenda_applied = bool(memory.topics)
        ticks = 0
        while True:
            await asyncio.sleep(BRAIN_TICK_S)
            try:
                # the background agenda just arrived: refresh so the interviewer
                # stops warming up and starts working the actual topics
                if not agenda_applied and memory.topics:
                    agenda_applied = True
                    self._refresh_system(context)

                if memory.status == "ending" and not farewell_sent:
                    farewell_sent = True
                    await task.queue_frames([
                        TTSSpeakFrame(
                            "Thank you, this has been genuinely valuable. "
                            "I am writing up your handover document now."),
                        EndFrame()])
                    return

                ticks += 1
                if ticks >= DIGEST_EVERY:
                    ticks = 0
                    if memory.undigested_turns() >= DIGEST_MIN_TURNS:
                        if await self._notetaker.digest(memory):
                            self._refresh_system(context)
                    self._compact(context)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.warning("brain loop error", session=memory.session_id,
                            error=str(e)[:200])

    def _tools_schema(self) -> ToolsSchema:
        return ToolsSchema(standard_tools=[
            FunctionSchema(name=d["name"], description=d["description"],
                           properties=d["parameters"]["properties"],
                           required=d["parameters"].get("required", []))
            for d in Interviewer.TOOL_DEFS])

    def _refresh_system(self, context: OpenAILLMContext):
        """Replace the system message in place - the INTERVIEW STATE inside it
        is the no-repeat guarantee, and appending instead would grow forever."""
        messages = context.get_messages()
        rest = [m for m in messages if m.get("role") != "system"]
        if not rest:
            rest = [{"role": "user", "content": "Please start the interview."}]
        context.set_messages(
            [{"role": "system",
              "content": self._interviewer.system_prompt()}] + rest)

    @staticmethod
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

    @staticmethod
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
