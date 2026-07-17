// Conversation history. Same reasoning as profile.js: RLS scopes every row to
// its owner, so this talks to supabase directly and the gateway stays
// stateless.
//
// Demo mode has no database. Rather than pretend, historyEnabled is false and
// the UI says so - a history that silently forgets is worse than none.

import { supabase, supabaseEnabled } from "./supabase";

export const historyEnabled = supabaseEnabled;

const TITLE_MAX = 60;

export function titleFor(question) {
  const clean = question.trim().replace(/\s+/g, " ");
  return clean.length > TITLE_MAX ? clean.slice(0, TITLE_MAX - 1) + "…" : clean;
}

export async function listConversations(limit = 50) {
  if (!supabaseEnabled) return [];
  const { data, error } = await supabase
    .from("conversations")
    .select("id, title, updated_at")
    .order("updated_at", { ascending: false })
    .limit(limit);
  if (error) throw new Error(error.message);
  return data ?? [];
}

export async function createConversation(userId, title) {
  if (!supabaseEnabled) return null;
  const { data, error } = await supabase
    .from("conversations")
    .insert({ user_id: userId, title })
    .select("id, title, updated_at")
    .single();
  if (error) throw new Error(error.message);
  return data;
}

// Rebuilds the turn shape Ask.jsx renders: a question paired with the answer
// that followed it. Messages are stored flat and alternating, which is what
// makes them cheap to append one at a time.
export async function loadTurns(conversationId) {
  if (!supabaseEnabled) return [];
  const { data, error } = await supabase
    .from("messages")
    .select("role, text, answer")
    .eq("conversation_id", conversationId)
    .order("created_at", { ascending: true });
  if (error) throw new Error(error.message);

  const turns = [];
  for (const row of data ?? []) {
    if (row.role === "user") {
      turns.push({ question: row.text, text: "", answer: null });
    } else if (turns.length) {
      const turn = turns[turns.length - 1];
      turn.text = row.text;
      turn.answer = row.answer;
    }
  }
  return turns;
}

export async function saveTurn(conversationId, question, text, answer) {
  if (!supabaseEnabled || !conversationId) return;
  const { error } = await supabase.from("messages").insert([
    { conversation_id: conversationId, role: "user", text: question },
    { conversation_id: conversationId, role: "assistant", text, answer },
  ]);
  if (error) throw new Error(error.message);
}

export async function renameConversation(id, title) {
  if (!supabaseEnabled) return;
  const { error } = await supabase
    .from("conversations").update({ title }).eq("id", id);
  if (error) throw new Error(error.message);
}

export async function deleteConversation(id) {
  if (!supabaseEnabled) return;
  // messages go with it: the FK is on delete cascade
  const { error } = await supabase.from("conversations").delete().eq("id", id);
  if (error) throw new Error(error.message);
}
