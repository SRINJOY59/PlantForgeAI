// Who the engineer is. Read straight from supabase rather than through the
// gateway: RLS already scopes a row to its owner, and the gateway has no
// business holding per-user state.

import { supabase, supabaseEnabled } from "./supabase";

export const JOB_TITLES = [
  "Reliability Engineer", "Process Engineer", "Maintenance Planner",
  "Inspection Engineer", "Shift Supervisor", "Instrumentation Engineer",
  "Plant Manager", "HSE Officer",
];

export const DEPARTMENTS = [
  "Maintenance", "Operations", "Process", "Inspection", "Instrumentation",
  "HSE", "Engineering",
];

export const UNITS = ["Unit 100", "Unit 200", "Unit 300"];

// Demo mode has no supabase to read from, but the profile drives real UI, so
// it gets a plausible engineer instead of nulls.
const DEMO_PROFILE = {
  id: "demo",
  full_name: "Demo Engineer",
  employee_id: "EMP-0001",
  job_title: "Reliability Engineer",
  department: "Maintenance",
  plant: "Demo Refinery",
  home_unit: "Unit 200",
  projects: ["P-101 seal reliability", "Unit 200 turnaround 2026"],
  expertise: ["Rotating equipment", "Vibration analysis"],
};

export async function fetchProfile(userId) {
  if (!supabaseEnabled) return DEMO_PROFILE;
  const { data, error } = await supabase
    .from("profiles").select("*").eq("id", userId).maybeSingle();
  if (error) throw new Error(error.message);
  // the signup trigger normally makes this row; upsert covers accounts that
  // predate the trigger being installed
  return data ?? { id: userId, projects: [], expertise: [] };
}

export async function saveProfile(userId, patch) {
  if (!supabaseEnabled) return { ...DEMO_PROFILE, ...patch };
  const { data, error } = await supabase
    .from("profiles")
    .upsert({ id: userId, ...patch, updated_at: new Date().toISOString() })
    .select()
    .single();
  if (error) throw new Error(error.message);
  return data;
}

export function displayName(profile, user) {
  return profile?.full_name || user?.email?.split("@")[0] || "Engineer";
}

export function initials(profile, user) {
  const name = displayName(profile, user);
  const parts = name.split(/[\s._-]+/).filter(Boolean);
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2))
    .toUpperCase();
}
