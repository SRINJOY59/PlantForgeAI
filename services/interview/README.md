# Interview — knowledge capture from retiring employees

A voice-agent exit interview. The employee clicks **Start Interviewing** in
the UI (`/app/interview`); a real-time voice conversation runs against an AI
interviewer that already knows their role, projects and equipment history, so
it only asks about what is *not* written down — workarounds, early-warning
signs, vendor quirks, who to call. When every topic is covered it writes a
knowledge-handover `README.md`, offers it for download, and feeds it through
PlantMind's normal ingestion pipeline so the knowledge becomes queryable in
Ask.

## How it works

```
UI (useProfile) ──POST /sessions {profile}──▶ interview service (:8002)
     context.py + graph_context.py: profile + Neo4j equipment/WO history
     service.py: LLM (MID) generates a 10-15 topic agenda ─▶ SessionMemory
UI ──PipecatClient──POST /api/offer──▶ SmallWebRTC (P2P, STUN only)
     bot.py: mic ─▶ Silero VAD ─▶ Deepgram STT ─▶ LLM (OpenRouter)
             ─▶ Deepgram TTS ─▶ speaker
     every 20s: notetaker (CHEAP) digests new turns ─▶ topic facts/coverage
                ─▶ INTERVIEW STATE block replaced in the system prompt
                   (this is the no-repeat guarantee)
     tools: mark_topic_covered / add_topic / finish_interview
end (tool | End button | disconnect) ─▶ finalize():
     README (MID) ─▶ data/interviews/exports/<session>/README.md
     stage_and_enqueue(source="interview:<employee_id>") ─▶ classify ─▶
     extract ─▶ resolve ─▶ graph ─▶ answerable in Ask
```

Session state (`data/interviews/sessions/<id>.json`) is the durable memory:
transcript, agenda, captured facts. A service restart mid-call loses the
audio leg but not the knowledge; the UI can reconnect into the same session.

## Files

| file | role |
|---|---|
| `main.py` | FastAPI app: sessions REST, `/api/offer` WebRTC signaling, `/debug/text` |
| `service.py` | session lifecycle, agenda generation, tool handlers, text loop, finalize |
| `bot.py` | Pipecat pipeline (voice only; imported lazily) |
| `memory.py` | topic agenda, notetaker digest, INTERVIEW STATE, JSON persistence |
| `context.py` / `graph_context.py` | profile + read-only Neo4j work context |
| `prompts.py` | agenda / interviewer / notetaker / README prompts |
| `readme_gen.py` | README generation, save, `stage_and_enqueue` ingestion |
| `config.py` | interview-only env keys (core `Settings` ignores unknown keys) |
| `auth.py` | Supabase JWT check, open in demo mode (mirrors the gateway) |

## Run

```bash
# once
.venv\Scripts\activate
pip install -r infra\docker\requirements\interview.txt

# backend - one command starts everything, interview included
python -m tools.serve

# UI
cd ui && npm install && npm run dev     # → http://localhost:5173/app/interview
```

`tools.serve` spawns `interview` alongside `gateway`/`retrieval`/`agents` as a
plain subprocess (see `SERVERS` in `tools/serve.py`) - no separate terminal
needed. For the containerized stack, `docker compose up` builds and starts
it as the `interview` service too (`docker-compose.yml`). To run just this
service standalone: `python -m uvicorn interview.main:app --port 8002`.

Env keys (appended to root `.env`):

| key | meaning |
|---|---|
| `DEEPGRAM_API_KEY` | STT + TTS. Empty ⇒ voice off, `/api/offer` returns 503 |
| `INTERVIEW_TTS_PROVIDER` | `deepgram` (default) \| `cartesia` \| `elevenlabs` |
| `INTERVIEW_LLM_MODEL` | override; empty ⇒ `LLM_MID` |
| `INTERVIEW_TEXT_MODE` | `1` ⇒ typed interview works with no Deepgram key |
| `INTERVIEW_PORT` / `INTERVIEW_DATA_DIR` | default `8002` / `data/interviews` |

`VITE_INTERVIEW_URL` (ui/.env) only if the service is not on
`http://localhost:8002`.

## Text mode (no key, no mic)

With `INTERVIEW_TEXT_MODE=1` and no `DEEPGRAM_API_KEY`, the Interview page
runs the same brain as a typed chat. Or via curl:

```bash
curl -X POST :8002/sessions -H "Content-Type: application/json" \
     -d '{"profile": {...}}'                     # → session_id + agenda
curl -X POST :8002/debug/text/<id> -d '{"text": "hello"}'
curl -X POST :8002/sessions/<id>/end             # → README generated
curl      :8002/sessions/<id>/readme
```

## Caveats

- `pipecat-ai` is pinned to **0.0.108** — its module paths move between
  releases; re-verify `bot.py` imports before bumping.
- Windows: `PipelineRunner(handle_sigint=False)` is required (no Unix
  signals).
- WebRTC is STUN-only P2P: fine on localhost/LAN; remote users would need a
  TURN server.
- `getUserMedia` needs a secure context: `localhost` or https.
- The realtime model must support tool calling on OpenRouter (the default
  `LLM_MID` does; `INTERVIEW_LLM_MODEL` is the escape hatch).
- `/api/offer` is authenticated by possession of a live `session_id` (minted
  by an authenticated `POST /sessions`) because the browser transport cannot
  attach an Authorization header to the signaling POST.
- If MinIO/Redis are down at finalize time the README is still written to
  disk; `POST /sessions/<id>/ingest` retries the pipeline push later.
