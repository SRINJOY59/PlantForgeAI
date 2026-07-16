// Client for the PlantMind gateway. Streaming endpoints use SSE: /ask/stream
// over fetch (POST bodies rule out EventSource), /alerts over EventSource.

const BASE = import.meta.env.VITE_GATEWAY_URL || "http://localhost:8000";

export async function ask(question) {
  const res = await fetch(`${BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
    headers: { "Content-Type": "application/json" },
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

export function subscribeAlerts(onAlert) {
  const source = new EventSource(`${BASE}/alerts`);
  source.addEventListener("alert", (e) => onAlert(JSON.parse(e.data)));
  return () => source.close();
}

export async function ingest(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/ingest`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`ingest failed: ${res.status}`);
  return res.json();
}

export async function metrics() {
  const res = await fetch(`${BASE}/metrics`);
  if (!res.ok) throw new Error(`metrics failed: ${res.status}`);
  return res.json();
}

export function documentUrl(docId) {
  return `${BASE}/documents/${docId}`;
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
