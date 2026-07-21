import { useCallback, useEffect, useRef, useState } from "react";
import {
  AudioLines, CheckCircle2, Circle, Download, Loader2, Mic, MicOff,
  PhoneOff, Send, Sparkles,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useProfile } from "../../state/ProfileContext";
import {
  checkHealth, createSession, endSession, fetchSkills, getSession,
  skillsDownloadUrl, sendDebugText, startVoice,
} from "../../lib/interview";

// idle -> preparing -> connecting -> live -> generating -> done
//                                 \-> error (recoverable back to idle)

// A one-frame silent WAV. Played synchronously inside the Start Interviewing
// click handler to "unlock" the <audio> element under the browser's user-
// gesture requirement - by the time the bot's real track arrives (after
// session creation + WebRTC negotiation), too much async time has passed
// for a fresh play() call to still count as user-initiated, and autoplay
// gets silently blocked otherwise.
const SILENT_WAV =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";

export default function Interview() {
  const { profile } = useProfile();
  const [phase, setPhase] = useState("idle");
  const [health, setHealth] = useState(null);
  const [session, setSession] = useState(null);      // GET /sessions/{id} view
  const [sessionId, setSessionId] = useState(null);
  const [turns, setTurns] = useState([]);            // {role, text, final}
  const [muted, setMuted] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [skills, setSkills] = useState(null);
  const [error, setError] = useState(null);
  const [textInput, setTextInput] = useState("");
  const [textBusy, setTextBusy] = useState(false);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const voiceRef = useRef(null);
  const scroller = useRef(null);
  const audioRef = useRef(null);

  const textMode = health && !health.voice_ready && health.text_mode;

  useEffect(() => {
    checkHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  // call timer
  useEffect(() => {
    if (phase !== "live") return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [phase]);

  // topic coverage + status polling while the interview is running
  useEffect(() => {
    if (!sessionId || !["live", "generating"].includes(phase)) return;
    const t = setInterval(async () => {
      try {
        const s = await getSession(sessionId);
        setSession(s);
        if (s.skills_ready) {
          setSkills(await fetchSkills(sessionId));
          setPhase("done");
        } else if (["generating", "ending"].includes(s.status) && phase === "live") {
          setPhase("generating");
        } else if (s.status === "failed") {
          setError(s.error || "the interview could not be finalized");
          setPhase("error");
        }
      } catch { /* transient poll failure - keep going */ }
    }, 3000);
    return () => clearInterval(t);
  }, [sessionId, phase]);

  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [turns]);

  // leaving the page mid-call still ends the interview cleanly
  useEffect(() => () => {
    voiceRef.current?.disconnect();
  }, []);

  const pushTurn = useCallback((role, text, final) => {
    if (!text?.trim()) return;
    setTurns((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      // interim user transcripts replace each other until final
      if (last && last.role === role && !last.final) {
        next[next.length - 1] = { role, text, final };
        return next;
      }
      next.push({ role, text, final });
      return next;
    });
  }, []);

  async function start() {
    if (!profile) return;
    setError(null);
    setAudioBlocked(false);
    // must happen synchronously, before any await, to count as part of
    // this click's user gesture
    if (audioRef.current) {
      audioRef.current.src = SILENT_WAV;
      audioRef.current.play().catch(() => {});
    }
    setPhase("preparing");
    try {
      const created = await createSession(profile);
      setSessionId(created.session_id);
      setSession({ topics: created.topics, status: "created" });
      if (textMode) {
        setPhase("live");
        return;
      }
      setPhase("connecting");
      voiceRef.current = await startVoice(created.session_id, {
        onBotReady: () => setPhase("live"),
        onUserTranscript: (d) => { if (d?.text) pushTurn("user", d.text, !!d.final); },
        onBotTranscript: (d) => { if (d?.text) pushTurn("assistant", d.text, true); },
        onTrackStarted: (track, participant) => {
          // The SmallWebRTC transport fires this with NO participant for the
          // bot's incoming audio, so an "is remote" check must treat an
          // absent participant as remote. Only skip our own local mic
          // (participant.local === true), which must not loop back to us.
          if (track.kind === "audio" && participant?.local !== true
              && audioRef.current) {
            audioRef.current.srcObject = new MediaStream([track]);
            audioRef.current.play()
              .then(() => setAudioBlocked(false))
              .catch(() => setAudioBlocked(true));
          }
        },
        onDisconnected: () => setPhase((p) => (p === "live" ? "generating" : p)),
        onError: (msg) => {
          setError(typeof msg === "string" ? msg : "voice connection failed");
          setPhase("error");
        },
      });
    } catch (e) {
      setError(e.message);
      setPhase("error");
    }
  }

  async function stop() {
    setPhase("generating");
    try { await endSession(sessionId); } catch { /* poll will catch up */ }
    await voiceRef.current?.disconnect();
    voiceRef.current = null;
  }

  function toggleMute() {
    const next = !muted;
    voiceRef.current?.setMuted(next);
    setMuted(next);
  }

  async function sendText(e) {
    e?.preventDefault();
    const text = textInput.trim();
    if (!text || textBusy) return;
    setTextInput("");
    setTextBusy(true);
    pushTurn("user", text, true);
    try {
      const res = await sendDebugText(sessionId, text);
      if (res.reply) pushTurn("assistant", res.reply, true);
      if (["ending", "generating"].includes(res.status)) setPhase("generating");
    } catch (err) {
      setError(err.message);
    } finally {
      setTextBusy(false);
    }
  }

  async function download() {
    const url = await skillsDownloadUrl(sessionId);
    const a = document.createElement("a");
    a.href = url;
    a.download = `skills_${profile?.employee_id || sessionId}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex h-full flex-col overflow-hidden" style={{ background: "var(--bg-surface)" }}>
      {/* always mounted so the ref is live before the bot's track arrives */}
      <audio ref={audioRef} autoPlay style={{ display: "none" }} />
      {phase === "idle" && <Welcome profile={profile} health={health} textMode={textMode} onStart={start} />}
      {(phase === "preparing" || phase === "connecting") && (
        <Centered>
          <Loader2 size={28} className="animate-spin" style={{ color: "var(--blue)" }} />
          <p className="mt-3 text-sm font-medium" style={{ color: "var(--text-md)" }}>
            {phase === "preparing"
              ? "Reading your work history and preparing the interview…"
              : "Connecting the voice line…"}
          </p>
          <p className="mt-1 text-xs" style={{ color: "var(--muted-lt)" }}>
            {phase === "connecting" && "Your browser will ask for microphone access."}
          </p>
        </Centered>
      )}
      {phase === "live" && (
        <Live
          turns={turns} session={session} seconds={seconds} muted={muted}
          textMode={textMode} textInput={textInput} textBusy={textBusy}
          audioBlocked={audioBlocked}
          scroller={scroller} onMute={toggleMute} onEnd={stop}
          onTextChange={setTextInput} onTextSend={sendText}
          onEnableAudio={() => {
            audioRef.current?.play()
              .then(() => setAudioBlocked(false))
              .catch(() => {});
          }}
        />
      )}
      {phase === "generating" && (
        <Centered>
          <Sparkles size={28} style={{ color: "var(--blue)" }} />
          <p className="mt-3 text-sm font-medium" style={{ color: "var(--text-md)" }}>
            Writing your knowledge handover document…
          </p>
          <p className="mt-1 text-xs" style={{ color: "var(--muted-lt)" }}>
            Distilling {turns.length} exchanges into a skills document. This takes a minute.
          </p>
        </Centered>
      )}
      {phase === "done" && (
        <Done skills={skills} session={session} onDownload={download} />
      )}
      {phase === "error" && (
        <Centered>
          <div className="card max-w-lg p-6 text-center">
            <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              The interview hit a problem
            </p>
            <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>{error}</p>
            <button className="btn-primary mt-4" onClick={() => setPhase("idle")}>
              Back
            </button>
          </div>
        </Centered>
      )}
    </div>
  );
}

function Centered({ children }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6">
      {children}
    </div>
  );
}

function Welcome({ profile, health, textMode, onStart }) {
  const offline = health === null;
  const noVoiceNoText = health && !health.voice_ready && !health.text_mode;
  return (
    <Centered>
      <div
        className="grid h-14 w-14 place-items-center rounded-2xl"
        style={{ background: "var(--blue)", boxShadow: "0 4px 14px rgba(122,84,160,0.35)" }}
      >
        <AudioLines size={26} className="text-white" />
      </div>
      <h1 className="page-title mt-4">Knowledge Capture Interview</h1>
      <p className="mt-2 max-w-xl text-center text-sm" style={{ color: "var(--muted)" }}>
        A voice interview that captures what only you know before you leave —
        the workarounds, the early-warning signs, the people to call. The agent
        already knows your projects and equipment history, so it will only ask
        about what isn't written down. At the end you get a handover document,
        and PlantForge.ai learns it too.
      </p>

      {profile && (
        <div className="card mt-5 w-full max-w-xl p-4">
          <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted-lt)" }}>
            Interviewing
          </p>
          <p className="mt-1 text-sm font-semibold" style={{ color: "var(--text)" }}>
            {profile.full_name} · {profile.job_title} · {profile.home_unit}
          </p>
          {(profile.projects?.length > 0 || profile.expertise?.length > 0) && (
            <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
              {[...(profile.projects || []), ...(profile.expertise || [])].join(" · ")}
            </p>
          )}
        </div>
      )}

      {offline && (
        <p className="mt-4 text-sm" style={{ color: "#dc2626" }}>
          Interview service unreachable — check that it is running on port 8003.
        </p>
      )}
      {noVoiceNoText && (
        <p className="mt-4 max-w-md text-center text-sm" style={{ color: "#dc2626" }}>
          Voice is disabled (DEEPGRAM_API_KEY not set) and text mode is off.
          Set the key, or INTERVIEW_TEXT_MODE=1 for a typed interview.
        </p>
      )}
      {textMode && (
        <p className="mt-4 text-xs" style={{ color: "var(--muted)" }}>
          No voice key configured — running as a typed interview.
        </p>
      )}

      <button
        className="btn-primary mt-5 flex items-center gap-2 px-6 py-2.5"
        onClick={onStart}
        disabled={!profile || offline || noVoiceNoText}
      >
        <Mic size={15} /> Start Interviewing
      </button>
    </Centered>
  );
}

function Live({ turns, session, seconds, muted, textMode, textInput, textBusy,
                audioBlocked, scroller, onMute, onEnd, onTextChange, onTextSend,
                onEnableAudio }) {
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {!textMode && audioBlocked && (
        <div
          className="flex items-center justify-center gap-3 px-4 py-2 text-xs font-medium"
          style={{ background: "#fef3c7", color: "#92400e" }}
        >
          Your browser blocked the interviewer's audio.
          <button
            className="rounded-md px-2.5 py-1 text-xs font-semibold text-white"
            style={{ background: "#92400e" }}
            onClick={onEnableAudio}
          >
            Enable sound
          </button>
        </div>
      )}
      {/* call bar */}
      <div
        className="flex items-center gap-3 px-5 py-3"
        style={{ background: "var(--bg-panel)", borderBottom: "1px solid var(--border)" }}
      >
        <span className="live-dot" />
        <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>
          Interview in progress
        </span>
        <span className="font-mono text-xs" style={{ color: "var(--muted-lt)" }}>
          {mm}:{ss}
        </span>
        <div className="flex-1" />
        {!textMode && (
          <button className="btn-outline flex items-center gap-1.5 text-xs" onClick={onMute}>
            {muted ? <MicOff size={13} /> : <Mic size={13} />}
            {muted ? "Unmute" : "Mute"}
          </button>
        )}
        <button
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-white"
          style={{ background: "#dc2626" }}
          onClick={onEnd}
        >
          <PhoneOff size={13} /> End Interview
        </button>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* transcript */}
        <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {turns.length === 0 && (
            <p className="mt-8 text-center text-sm" style={{ color: "var(--muted-lt)" }}>
              {textMode ? "Say hello to begin." : "The interviewer is about to greet you…"}
            </p>
          )}
          {turns.map((t, i) => (
            <div key={i} className={`mb-3 flex ${t.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className="max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed"
                style={t.role === "user"
                  ? { background: "var(--blue)", color: "white", opacity: t.final ? 1 : 0.7 }
                  : { background: "var(--bg-panel)", color: "var(--text)",
                      border: "1px solid var(--border)" }}
              >
                {t.text}
              </div>
            </div>
          ))}
          {textMode && (
            <form onSubmit={onTextSend} className="sticky bottom-0 mt-4 flex gap-2 pb-1">
              <input
                className="input flex-1"
                placeholder="Type your answer…"
                value={textInput}
                onChange={(e) => onTextChange(e.target.value)}
                disabled={textBusy}
                autoFocus
              />
              <button className="btn-primary flex items-center gap-1.5" disabled={textBusy}>
                {textBusy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              </button>
            </form>
          )}
        </div>

        {/* topic coverage */}
        <TopicPanel session={session} />
      </div>
    </div>
  );
}

function TopicPanel({ session }) {
  const topics = session?.topics || [];
  const covered = topics.filter((t) => t.status === "covered").length;
  const pct = Math.round((session?.overall_coverage || 0) * 100);
  return (
    <aside
      className="w-72 min-w-72 overflow-y-auto px-4 py-4"
      style={{ background: "var(--bg-panel)", borderLeft: "1px solid var(--border)" }}
    >
      <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted-lt)" }}>
        Coverage · {covered}/{topics.length} topics
      </p>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
        <div className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: "var(--blue)" }} />
      </div>
      <div className="mt-4 flex flex-col gap-2">
        {topics.map((t) => (
          <div key={t.id} className="flex items-start gap-2">
            {t.status === "covered"
              ? <CheckCircle2 size={14} className="mt-0.5 flex-shrink-0" style={{ color: "#16a34a" }} />
              : t.status === "partial"
                ? <Circle size={14} className="mt-0.5 flex-shrink-0" style={{ color: "var(--blue)" }} />
                : <Circle size={14} className="mt-0.5 flex-shrink-0" style={{ color: "var(--muted-lt)" }} />}
            <div>
              <p className="text-xs font-medium leading-snug"
                style={{ color: t.status === "covered" ? "var(--muted)" : "var(--text-md)" }}>
                {t.title}
              </p>
              <span className="text-[10px] uppercase tracking-wide" style={{ color: "var(--muted-lt)" }}>
                {t.category}{t.facts_count > 0 && ` · ${t.facts_count} facts`}
              </span>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}

function Done({ skills, session, onDownload }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="page-title">Skills & Knowledge Handover</h1>
            <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
              {session?.staging_key
                ? "Saved and sent to the PlantForge.ai pipeline — it will be answerable in Ask shortly."
                : "Saved locally. The ingestion pipeline was unreachable — retry from the backend when it's up."}
            </p>
          </div>
          <button className="btn-primary flex items-center gap-2" onClick={onDownload}>
            <Download size={14} /> Download skills.md
          </button>
        </div>
        <div className="card prose prose-sm mt-5 max-w-none p-6 dark:prose-invert">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{skills || ""}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
