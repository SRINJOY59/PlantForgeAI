// Strip citation markers before a worker sees or HEARS an answer. Reading
// "[doc:39ceb0...]" aloud over TTS is meaningless at the equipment, and the
// backend already tells the worker persona to omit them - this is the belt to
// that suspenders, catching any the model still emits. Shared by both field
// views (Copilot and Ask).
export function cleanForField(t) {
  return (t || "")
    .replace(/\[doc:[^\]]*\]/gi, "")
    .replace(/\[[a-f0-9]{6,}(?:\s+p\d+)?\]/gi, "")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/ +([.,;:])/g, "$1")
    .trim();
}
