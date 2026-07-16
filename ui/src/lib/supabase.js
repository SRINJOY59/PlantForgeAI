import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

// When Supabase isn't configured yet the app still runs in a demo mode -
// auth is skipped and the brain (gateway) works on its own.
export const supabaseEnabled = Boolean(url && anonKey);

export const supabase = supabaseEnabled
  ? createClient(url, anonKey)
  : null;
