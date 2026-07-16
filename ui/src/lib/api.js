// Client for the PlantMind gateway. Every call carries the Supabase JWT; the
// gateway verifies it (this side only attaches it). Streaming uses SSE over
// fetch rather than EventSource - EventSource cannot send an Authorization
// header, and a token in the query string would leak into logs and history.

import { supabase } from "./supabase";

const BASE = import.meta.env.VITE_GATEWAY_URL || "http://localhost:8000";

async function authHeaders() {
  if (!supabase) return {};                 // demo mode: gateway is open
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function ask(question) {
  const res = await fetch(`${BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error(`ask failed: ${res.status}`);
  return res.json();
}

// Streams the answer. Calls onToken(text) for each delta and returns the
// final answer object (citations, mode, confidence) from the 'done' event.
export async function askStream(question, onToken, signal) {
  const res = await fetch(`${BASE}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!res.ok) throw new Error(`stream failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done = null;

  while (true) {
    const { value, done: finished } = await reader.read();
    if (finished) break;
    buffer += decoder.decode(value, { stream: true });

    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const event = parseSse(frame);
      if (!event) continue;
      if (event.name === "token") onToken(event.data.text);
      else if (event.name === "done") done = event.data;
    }
  }
  return done;
}

// after=0 replays the alerts already on the stream before following live
// ones; the default ('$') would only ever show alerts raised after connecting,
// so a freshly opened feed would look empty.
//
// fetch instead of EventSource so the JWT rides in a header. EventSource
// reconnects on its own; here we do it explicitly, resuming from the last
// alert id so a dropped connection doesn't replay or skip.
export function subscribeAlerts(onAlert, after = "0") {
  const control = new AbortController();
  let cursor = after;

  (async () => {
    while (!control.signal.aborted) {
      try {
        const res = await fetch(
          `${BASE}/alerts?after=${encodeURIComponent(cursor)}`,
          { headers: await authHeaders(), signal: control.signal });
        if (!res.ok) throw new Error(`alerts failed: ${res.status}`);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split("\n\n");
          buffer = frames.pop() || "";
          for (const frame of frames) {
            const event = parseSse(frame);
            if (event?.name !== "alert") continue;
            cursor = event.data.id ?? cursor;
            onAlert(event.data);
          }
        }
      } catch (e) {
        if (control.signal.aborted) return;
      }
      await new Promise((r) => setTimeout(r, 3000));   // backoff, then resume
    }
  })();

  return () => control.abort();
}

export async function ingest(file) {
  const form = new FormData();
  form.append("file", file);
  // no Content-Type: the browser sets the multipart boundary itself
  const res = await fetch(`${BASE}/ingest`, {
    method: "POST", body: form, headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`ingest failed: ${res.status}`);
  return res.json();
}

export async function metrics() {
  const res = await fetch(`${BASE}/metrics`, { headers: await authHeaders() });
  if (!res.ok) throw new Error(`metrics failed: ${res.status}`);
  return res.json();
}

export function documentUrl(docId) {
  return `${BASE}/documents/${docId}`;
}

// /documents needs the JWT, but an <iframe src> can't carry a header - so
// fetch the bytes with auth and hand back a blob URL. Caller must revoke it.
export async function fetchDocumentUrl(docId) {
  const res = await fetch(`${BASE}/documents/${docId}`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`document failed: ${res.status}`);
  return URL.createObjectURL(await res.blob());
}

export async function getGraph() {
  const res = await fetch(`${BASE}/graph`, { headers: await authHeaders() });
  if (!res.ok) throw new Error(`graph failed: ${res.status}`);
  return res.json();
}

function parseSse(frame) {
  let name = "message";
  const dataLines = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  try {
    return { name, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}
