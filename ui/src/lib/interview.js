// Client for the knowledge-capture interview service (host port 8003). REST for
// session lifecycle (same JWT-in-header pattern as api.js); the voice leg is
// a Pipecat SmallWebRTC connection negotiated through /api/offer, where the
// session id - minted by an authenticated call - is the credential, because
// the transport's signaling POST cannot carry an Authorization header.

import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { supabase } from "./supabase";
import { resolveBackendUrl } from "./backendUrl";

// 8003, not 8002: agents-api (the MOC backend) owns host 8002. Override with
// VITE_INTERVIEW_URL in deployments that map the interview service elsewhere -
// in the k8s deployment it shares the API host under a /interview prefix, which
// is why the container runs with --root-path /interview.
//
// Unset, this falls back to localhost, which is right for local dev and is
// exactly what made the deployed Interview page look like a dead service: the
// browser was being told to call the user's own machine. resolveBackendUrl also
// keeps the scheme in step with the page, so an https console cannot be handed
// an http backend it is forbidden to call.
const BASE = resolveBackendUrl(import.meta.env.VITE_INTERVIEW_URL,
                               "http://localhost:8003");

async function authHeaders() {
  if (!supabase) return {};                 // demo mode: service is open
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(await authHeaders()),
      ...options.headers,
    },
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* keep */ }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res;
}

export async function checkHealth() {
  const res = await fetch(`${BASE}/health`);
  if (!res.ok) throw new Error(`interview service unreachable: ${res.status}`);
  return res.json();
}

export async function createSession(profile) {
  const res = await request("/sessions", {
    method: "POST", body: JSON.stringify({ profile }),
  });
  return res.json();
}

export async function getSession(sessionId) {
  const res = await request(`/sessions/${sessionId}`);
  return res.json();
}

export async function endSession(sessionId) {
  const res = await request(`/sessions/${sessionId}/end`, { method: "POST" });
  return res.json();
}

export async function fetchSkills(sessionId) {
  const res = await request(`/sessions/${sessionId}/skills`);
  return res.text();
}

// /skills needs the JWT, and an <a href> can't carry a header - same blob
// trick as fetchDocumentUrl in api.js. Caller must revoke the URL.
export async function skillsDownloadUrl(sessionId) {
  const res = await request(`/sessions/${sessionId}/skills?download=1`);
  return URL.createObjectURL(await res.blob());
}

export async function sendDebugText(sessionId, text) {
  const res = await request(`/debug/text/${sessionId}`, {
    method: "POST", body: JSON.stringify({ text }),
  });
  return res.json();
}

// Opens the WebRTC leg. callbacks: onConnected, onDisconnected, onBotReady,
// onUserTranscript({text, final}), onBotTranscript({text}), onError(msg).
// Returns { disconnect, setMuted }.
export async function startVoice(sessionId, callbacks = {}) {
  // Fetch the ICE servers (STUN + TURN with a fresh, time-limited credential).
  // The browser's media must relay through the same TURN as the bot's, or —
  // behind a load balancer with no direct path — the two never connect. If the
  // fetch fails we fall back to a public STUN so local/direct networks still work.
  let iceServers = [{ urls: "stun:stun.l.google.com:19302" }];
  try {
    const res = await fetch(`${BASE}/api/turn`);
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data.iceServers) && data.iceServers.length) {
        iceServers = data.iceServers;
      }
    }
  } catch { /* keep the STUN fallback */ }

  const transport = new SmallWebRTCTransport({
    connectionUrl: `${BASE}/api/offer?session_id=${sessionId}`,
    iceServers,
  });
  const client = new PipecatClient({
    transport,
    enableMic: true,
    enableCam: false,
    callbacks: {
      onConnected: () => callbacks.onConnected?.(),
      onDisconnected: () => callbacks.onDisconnected?.(),
      onBotReady: () => callbacks.onBotReady?.(),
      onUserTranscript: (data) => callbacks.onUserTranscript?.(data),
      onBotTranscript: (data) => callbacks.onBotTranscript?.(data),
      onError: (message) => callbacks.onError?.(message),
      // Neither SDK auto-plays the remote track - it just hands it over.
      // Without this, the bot's speech (and any local echo) never reaches
      // a speaker even though the data-channel transcript flows fine.
      onTrackStarted: (track, participant) =>
        callbacks.onTrackStarted?.(track, participant),
    },
  });

  await client.connect();

  return {
    disconnect: async () => {
      try { await client.disconnect(); } catch { /* already closed */ }
    },
    setMuted: (muted) => client.enableMic(!muted),
  };
}
