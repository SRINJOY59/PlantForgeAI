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

// Wrapper to automatically catch 401 Unauthorized errors (expired token),
// fetch a fresh token from Supabase in the background, and retry the request.
async function fetchWithAuth(url, options = {}) {
  let res = await fetch(url, options);
  if (res.status === 401 && supabase) {
    const { data, error } = await supabase.auth.refreshSession();
    if (!error && data?.session) {
      const headers = {
        ...options.headers,
        Authorization: `Bearer ${data.session.access_token}`,
      };
      res = await fetch(url, { ...options, headers });
    }
  }
  return res;
}

// The thread travels with the question - the backend keeps no session, so a
// follow-up like "what about its sibling?" is only answerable if we send the
// turns that gave it meaning. Last few only: the gateway caps it anyway, and
// older turns just drag stale tags into a question that has moved on.
const HISTORY_TURNS = 4;

export function toHistory(turns) {
  return turns
    .filter((t) => t.answer && !t.error)      // a failed turn explains nothing
    .slice(-HISTORY_TURNS)
    .map((t) => ({ question: t.question, answer: t.text }));
}

export async function ask(question, history = []) {
  const res = await fetchWithAuth(`${BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ question, history }),
  });
  if (!res.ok) throw new Error(`ask failed: ${res.status}`);
  return res.json();
}

// Ask for an LLM root-cause analysis of one live diagnosis. Fire-and-forget:
// the agents runtime runs it and the result arrives over the telemetry
// WebSocket as a { type: "investigation", diagnosis_id } message.
export async function investigateDiagnosis(diagId) {
  const res = await fetchWithAuth(
    `${BASE}/diagnostics/${encodeURIComponent(diagId)}/investigate`, {
      method: "POST",
      headers: { ...(await authHeaders()) },
    });
  if (!res.ok) throw new Error(`investigate failed: ${res.status}`);
  return res.json();
}

export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetchWithAuth(`${BASE}/ingest`, {
    method: "POST",
    headers: { ...(await authHeaders()) },
    body: formData,
  });
  if (!res.ok) {
    let errMsg = `Upload failed: ${res.status}`;
    try {
      const errJson = await res.json();
      errMsg = errJson.detail || errMsg;
    } catch {
      try {
        const errText = await res.text();
        errMsg = errText || errMsg;
      } catch {}
    }
    throw new Error(errMsg);
  }
  return res.json();
}

// Streams the answer. Calls onToken(text) for each delta and returns the
// final answer object (citations, mode, confidence) from the 'done' event.
export async function askStream(question, onToken, history = [], alertContext = null, signal = null, persona = null) {
  const res = await fetchWithAuth(`${BASE}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ question, history, alert_context: alertContext, persona }),
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
export async function getInitialAlerts() {
  try {
    const res = await fetchWithAuth(`${BASE}/initial-alerts`, { headers: await authHeaders() });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export function subscribeAlerts(onAlert, after = "0") {
  const control = new AbortController();
  let cursor = after;

  (async () => {
    while (!control.signal.aborted) {
      try {
        const res = await fetchWithAuth(
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
  const res = await fetchWithAuth(`${BASE}/ingest`, {
    method: "POST", body: form, headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`ingest failed: ${res.status}`);
  return res.json();
}

// An engineer overturning something we said. It goes in as a document and
// comes back as graph facts at the human tier - so this is the one call in the
// app that changes what the plant knows. The author is not sent: the gateway
// takes it off the verified token.
export async function submitCorrection({ question, answer, correction, citedDocs }) {
  const res = await fetchWithAuth(`${BASE}/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ question, answer, correction,
                           cited_docs: citedDocs ?? [] }),
  });
  if (!res.ok) throw new Error(`correction failed: ${res.status}`);
  return res.json();
}

// A proposed change, assessed before it is made. The agents service walks the
// graph the plant already holds - connections, failure history, governing
// clauses, the documents that mention the asset - and returns what the change
// would touch. Slower than a question by design (several tool calls), and it
// never returns a verdict: approving a change is a competent person's
// signature, not the model's.
export async function assessChange({ tag, summary }) {
  const res = await fetchWithAuth(`${BASE}/moc/assess`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ tag, summary }),
  });
  if (!res.ok) throw new Error(`assessment failed: ${res.status}`);
  return res.json();
}

// The streamed assessment. onStep(tool) fires as the agent gathers evidence,
// onToken(text) as the assessment is written; the resolved value is the final
// ImpactAssessment from the 'done' event. Same SSE-over-fetch shape as
// askStream, for the same reason: the JWT rides in a header.
export async function assessChangeStream({ tag, summary }, { onStep, onToken } = {}) {
  const res = await fetchWithAuth(`${BASE}/moc/assess/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ tag, summary }),
  });
  if (!res.ok) throw new Error(`assessment failed: ${res.status}`);

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
      if (event.name === "step") onStep?.(event.data.tool);
      else if (event.name === "token") onToken?.(event.data.text);
      else if (event.name === "done") done = event.data;
    }
  }
  return done;
}

export async function generateReport({ tag }) {
  const res = await fetchWithAuth(`${BASE}/reports/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ tag }),
  });
  if (!res.ok) throw new Error(`report generation failed: ${res.status}`);
  return res.json();
}

export async function draftPermitStream({ tag, workDescription, requestedBy }, { onStep, onToken } = {}) {
  const res = await fetchWithAuth(`${BASE}/permit/draft/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ tag, work_description: workDescription, requested_by: requestedBy }),
  });
  if (!res.ok) throw new Error(`permit drafting failed: ${res.status}`);

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
      if (event.name === "step") onStep?.(event.data.tool);
      else if (event.name === "token") onToken?.(event.data.text);
      else if (event.name === "done") done = event.data;
    }
  }
  return done;
}

export async function metrics() {
  const res = await fetchWithAuth(`${BASE}/metrics`, { headers: await authHeaders() });
  if (!res.ok) throw new Error(`metrics failed: ${res.status}`);
  return res.json();
}

export function documentUrl(docId) {
  return `${BASE}/documents/${docId}`;
}

// /documents/{id}/url returns a short-lived presigned URL from MinIO, bypassing
// the gateway proxy to eliminate bandwidth bottlenecks on large PDFs.
export async function fetchDocumentUrl(docId) {
  const res = await fetchWithAuth(`${BASE}/documents/${docId}/url`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`document failed: ${res.status}`);
  const data = await res.json();
  // filename comes back too: storage always knows it (the key is
  // raw/<doc_id>/<filename>), so it is the reliable name even when the
  // citation that got us here only carried a content hash.
  return { url: data.url, filename: data.filename ?? null };
}

export async function getGraph() {
  const res = await fetchWithAuth(`${BASE}/graph`, { headers: await authHeaders() });
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

// The plant's statutory position: every obligation with a due date, its status
// computed server-side so the summary cards and the list cannot disagree.
export async function getCompliance() {
  const res = await fetchWithAuth(`${BASE}/compliance`, { headers: await authHeaders() });
  if (!res.ok) throw new Error(`compliance failed: ${res.status}`);
  return res.json();
}

// Turn one due obligation into a preventive (PM02) work-order draft. Only the
// item id goes over the wire - the obligation's own facts are re-read from the
// graph, so a client cannot draft work against an asset it never looked at.
export async function scheduleInspection(itemId) {
  const res = await fetchWithAuth(`${BASE}/compliance/schedule`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ item_id: itemId }),
  });
  if (!res.ok) throw new Error(`schedule failed: ${res.status}`);
  return res.json();
}

export async function notifyComplianceSlack(item) {
  const res = await fetchWithAuth(`${BASE}/compliance/notify-slack`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify(item),
  });
  if (!res.ok) throw new Error(`notify-slack failed: ${res.status}`);
  return res.json();
}

export async function getSlackStatus() {
  const res = await fetchWithAuth(`${BASE}/system/slack/status`, { headers: await authHeaders() });
  if (!res.ok) return { enabled: false, configured: false };
  return res.json();
}

export async function testSlackNotification() {
  const res = await fetchWithAuth(`${BASE}/system/slack/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
  });
  if (!res.ok) throw new Error(`test-slack failed: ${res.status}`);
  return res.json();
}

// Approve or reject a drafted work order. The approver is not sent - the
// gateway takes it off the verified token, the same way a correction's author
// is established rather than asserted.
export async function decideWorkOrder(draftId, decision) {
  const res = await fetchWithAuth(`${BASE}/work-orders/${encodeURIComponent(draftId)}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ decision }),
  });
  if (!res.ok) throw new Error(`decision failed: ${res.status}`);
  return res.json();
}

export function subscribeDraftWorkOrders(onWorkOrder, after = "0") {
  const control = new AbortController();
  let cursor = after;

  (async () => {
    while (!control.signal.aborted) {
      try {
        const res = await fetchWithAuth(
          `${BASE}/work-orders/drafts?after=${encodeURIComponent(cursor)}`,
          { headers: await authHeaders(), signal: control.signal });
        if (!res.ok) throw new Error(`work orders failed: ${res.status}`);

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
            if (event?.name !== "work_order") continue;
            cursor = event.data.id ?? cursor;
            onWorkOrder(event.data);
          }
        }
      } catch (e) {
        if (control.signal.aborted) return;
      }
      await new Promise((r) => setTimeout(r, 3000));
    }
  })();

  return () => control.abort();
}

// ─── Simulation API extensions ──────────────────────────────────────────────

export async function getEnvelopes() {
  const res = await fetchWithAuth(`${BASE}/sim/envelopes`);
  if (!res.ok) throw new Error(`failed to get envelopes: ${res.status}`);
  return res.json();
}

export async function updateLimit(tagId, limits) {
  const res = await fetchWithAuth(`${BASE}/sim/limits/${encodeURIComponent(tagId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify(limits),
  });
  if (!res.ok) throw new Error(`failed to update limit for ${tagId}: ${res.status}`);
  return res.json();
}

export async function getLimitsAudit() {
  const res = await fetchWithAuth(`${BASE}/sim/limits/audit`, { headers: await authHeaders() });
  if (!res.ok) throw new Error(`failed to get limits audit: ${res.status}`);
  return res.json();
}

export async function simControl(unit, action) {
  const res = await fetchWithAuth(`${BASE}/sim/${unit}/${action}`, {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`simControl ${unit} ${action} failed: ${res.status}`);
  return res.json();
}

export async function simFault(unit, fault, tag = null, stage = null, value = null) {
  const res = await fetchWithAuth(`${BASE}/sim/${unit}/fault`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ fault, tag, stage, value }),
  });
  if (!res.ok) throw new Error(`simFault ${unit} failed: ${res.status}`);
  return res.json();
}

/** TEP-specific: Inject or clear an IDV fault by number (1-21). */
export async function simIdv(idv, active = true) {
  const res = await fetchWithAuth(`${BASE}/sim/tep/idv`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ idv, active }),
  });
  if (!res.ok) throw new Error(`simIdv IDV-${idv} failed: ${res.status}`);
  return res.json();
}

export async function getSimStatus(unit = "tep") {
  const res = await fetchWithAuth(`${BASE}/sim/${unit}/status`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`getSimStatus ${unit} failed: ${res.status}`);
  return res.json();
}


export function subscribeSimTelemetry(onMessage, unit = null) {
  let active = true;
  let ws = null;
  let backoff = 1000;

  async function connect() {
    if (!active) return;
    try {
      const headers = await authHeaders();
      const token = headers.Authorization ? headers.Authorization.replace("Bearer ", "") : "";
      const wsBase = BASE.replace(/^http/, "ws");
      let url = `${wsBase}/ws/plant-telemetry?token=${encodeURIComponent(token)}`;
      if (unit) url += `&unit=${encodeURIComponent(unit)}`;

      ws = new WebSocket(url);
      ws.onmessage = (event) => {
        if (!active) return;
        try {
          const data = JSON.parse(event.data);
          onMessage(data);
        } catch (e) {}
      };
      ws.onopen = () => {
        backoff = 1000;
      };
      ws.onclose = () => {
        if (!active) return;
        setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, 30000);
      };
      ws.onerror = () => {
        if (ws) ws.close();
      };
    } catch (err) {
      if (active) {
        setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, 30000);
      }
    }
  }

  connect();

  return () => {
    active = false;
    if (ws) ws.close();
  };
}


// ---------------------------------------------------------------- diagnostics
export async function fetchFaultLibrary() {
  const headers = await authHeaders();
  const res = await fetchWithAuth(`${BASE}/diagnostics/library`, { headers });
  if (!res.ok) throw new Error(`Fault library fetch failed: ${res.status}`);
  return res.json();
}

// --------------------------------------------------------------- field copilot
// The worker persona's endpoints. Asset scoping + live state + a multilingual,
// asset-aware grounded answer that reuses the same SSE shape as askStream.

export async function fieldAssets() {
  const res = await fetchWithAuth(`${BASE}/field/assets`, { headers: await authHeaders() });
  if (!res.ok) throw new Error(`field assets failed: ${res.status}`);
  const data = await res.json();
  return data.assets ?? [];
}

export async function fieldAssetContext(tag) {
  const res = await fetchWithAuth(
    `${BASE}/field/asset/${encodeURIComponent(tag)}/context`,
    { headers: await authHeaders() });
  if (!res.ok) throw new Error(`field asset context failed: ${res.status}`);
  return res.json();
}

export async function fieldLanguages() {
  const res = await fetchWithAuth(`${BASE}/field/languages`, { headers: await authHeaders() });
  if (!res.ok) throw new Error(`field languages failed: ${res.status}`);
  const data = await res.json();
  return data.languages ?? [];
}

// Streams an asset-scoped answer in the worker's language. Same SSE contract as
// askStream: onToken(delta) per chunk, resolves to the final answer object.
export async function fieldAskStream(question, onToken, { asset = null, lang = "en", history = [], signal = null } = {}) {
  const res = await fetchWithAuth(`${BASE}/field/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ question, asset, lang, history }),
    signal,
  });
  if (!res.ok) throw new Error(`field ask failed: ${res.status}`);

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
