// Voice for the Field Copilot, built on the browser's native Web Speech API:
// speechSynthesis for spoken answers, SpeechRecognition for spoken questions.
// Native on purpose - it is multilingual, on-device, needs no backend and no
// per-call cost, and works on the phones field workers actually carry. A
// server-side TTS (e.g. Google Cloud TTS) can later swap in behind speak()
// without the UI changing.
//
// Everything degrades quietly: on a browser without a given capability the
// support check returns false and the UI hides the control rather than erroring.

const synth = typeof window !== "undefined" ? window.speechSynthesis : null;
const Recognition =
  typeof window !== "undefined"
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null;

export function speechSupported() {
  return Boolean(synth);
}

export function recognitionSupported() {
  return Boolean(Recognition);
}

// Voices load asynchronously in most browsers: the first getVoices() is often
// empty until the 'voiceschanged' event fires. Cache them and resolve once.
let _voices = [];
function loadVoices() {
  if (!synth) return Promise.resolve([]);
  const now = synth.getVoices();
  if (now && now.length) {
    _voices = now;
    return Promise.resolve(now);
  }
  return new Promise((resolve) => {
    const handler = () => {
      _voices = synth.getVoices();
      synth.removeEventListener("voiceschanged", handler);
      resolve(_voices);
    };
    synth.addEventListener("voiceschanged", handler);
    // Safety timeout: some engines never fire the event but do populate later.
    setTimeout(() => resolve(synth.getVoices() || []), 1000);
  });
}

// Prime the cache as soon as the module loads.
if (synth) loadVoices();

// Pick the best voice for a BCP-47 code: exact match first (e.g. "hi-IN" for
// "hi"), then the base language, then whatever the engine defaults to.
function pickVoice(voices, lang) {
  if (!voices.length) return null;
  const base = lang.split("-")[0].toLowerCase();
  return (
    voices.find((v) => v.lang && v.lang.toLowerCase() === lang.toLowerCase()) ||
    voices.find((v) => v.lang && v.lang.toLowerCase().startsWith(base)) ||
    null
  );
}

/**
 * Speak `text` in `lang` (BCP-47, e.g. "en", "hi", "bn"). Cancels any answer
 * still being spoken first, so tapping a new question never overlaps the last.
 * Returns a promise that resolves when speech ends (or immediately if TTS is
 * unsupported). onBoundary, if given, fires as the engine advances - handy for
 * a "speaking" indicator.
 */
export async function speak(text, lang = "en", { onEnd } = {}) {
  if (!synth || !text) return;
  synth.cancel();
  const voices = _voices.length ? _voices : await loadVoices();
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = lang;
  const voice = pickVoice(voices, lang);
  if (voice) utter.voice = voice;
  utter.rate = 1.0;
  utter.pitch = 1.0;
  return new Promise((resolve) => {
    utter.onend = () => { onEnd?.(); resolve(); };
    utter.onerror = () => { onEnd?.(); resolve(); };
    synth.speak(utter);
  });
}

export function stopSpeaking() {
  if (synth) synth.cancel();
}

export function isSpeaking() {
  return Boolean(synth && synth.speaking);
}

/**
 * Create a speech recognizer bound to a language. Returns { start, stop,
 * abort }. Callbacks:
 *   onResult(text, isFinal) - interim and final transcripts
 *   onEnd()                  - recognition stopped (mic released)
 *   onError(err)             - permission denied, no-speech, etc.
 *
 * One utterance per start (continuous = false): a field worker asks one thing,
 * the mic releases, the question sends. That is calmer than an always-on mic
 * and avoids draining the battery on a listening loop.
 */
export function createRecognizer(lang = "en", { onResult, onEnd, onError } = {}) {
  if (!Recognition) return null;
  const rec = new Recognition();
  rec.lang = lang;
  rec.continuous = false;
  rec.interimResults = true;
  rec.maxAlternatives = 1;

  rec.onresult = (event) => {
    let interim = "";
    let final = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const r = event.results[i];
      if (r.isFinal) final += r[0].transcript;
      else interim += r[0].transcript;
    }
    if (final) onResult?.(final, true);
    else if (interim) onResult?.(interim, false);
  };
  rec.onend = () => onEnd?.();
  rec.onerror = (e) => onError?.(e.error || "recognition-error");

  return {
    start: () => { try { rec.start(); } catch { /* already started */ } },
    stop: () => { try { rec.stop(); } catch { /* already stopped */ } },
    abort: () => { try { rec.abort(); } catch { /* noop */ } },
  };
}
