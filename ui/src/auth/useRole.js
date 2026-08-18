// Reads the user's app_role from the Supabase access token without an extra
// round-trip. The custom_jwt_claims Postgres hook stamps the role into every
// token at mint time, so decoding it here is always consistent with what the
// gateway will enforce on the same token.
//
// FALLBACK: if the JWT carries no app_role (hook not registered, or user logged
// in before the hook was set up), we fetch the role directly from the profiles
// table. This costs one Supabase round-trip but only happens once per session
// until the user re-logs with a hook-minted token.
//
// Role hierarchy (least → most privileged):
//   worker    → Field Copilot only (separate mobile persona, own /field shell)
//   operator  → Ask, Alerts, Documents read
//   planner   → + Connectors read
//   engineer  → + Graph, Compliance, MoC, Interview, doc upload
//   admin     → full access + Connectors write, user management
//
// 'worker' is rank 0 so operator+ gates exclude it, but it is a *separate
// persona*: a worker is routed to /field, never the engineer /app console.
// Kept in sync with services/gateway/auth.py ROLE_HIERARCHY.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "./AuthProvider";
import { supabase, supabaseEnabled } from "../lib/supabase";

export const ROLE_HIERARCHY = ["worker", "operator", "planner", "engineer", "admin"];

// The field persona. Kept as its own predicate rather than a rank check because
// "is this a worker" is a routing question (which shell), not a privilege one.
export const WORKER_ROLE = "worker";

/** Decode the app_role from a raw JWT string. Returns null if not present. */
export function roleFromJwt(token) {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const claims = JSON.parse(json);
    const role =
      claims?.app_metadata?.app_role ??
      claims?.app_role ??
      null;
    return role && ROLE_HIERARCHY.includes(role) ? role : null;
  } catch {
    return null;
  }
}

/**
 * Returns the current user's app_role string.
 *
 * Priority:
 *  1. JWT claim (hook-minted, zero cost)         → instant
 *  2. Supabase profiles table fetch (fallback)   → one round-trip
 *  3. "operator" (safe default)
 */
export function useRole() {
  const { session, user, demoMode } = useAuth();
  const [dbRole, setDbRole] = useState(null);

  // Extract role from JWT on every session change
  const jwtRole = useMemo(() => {
    if (demoMode) return "engineer";
    if (!session?.access_token) return null;
    return roleFromJwt(session.access_token);
  }, [session, demoMode]);

  // Fallback: fetch from DB when JWT carries no role (hook not set up yet)
  useEffect(() => {
    if (jwtRole || !supabaseEnabled || !user?.id) {
      setDbRole(null);
      return;
    }
    let live = true;
    supabase
      .from("profiles")
      .select("app_role")
      .eq("id", user.id)
      .maybeSingle()
      .then(({ data }) => {
        if (live && data?.app_role && ROLE_HIERARCHY.includes(data.app_role)) {
          setDbRole(data.app_role);
        }
      });
    return () => { live = false; };
  }, [jwtRole, user?.id]);

  if (demoMode) return "engineer";
  return jwtRole ?? dbRole ?? "operator";
}

/**
 * Returns true if the current user's role is >= minRole in the hierarchy.
 *
 * Example: const canUpload = useHasRole("engineer");
 */
export function useHasRole(minRole) {
  const role = useRole();
  const userRank = ROLE_HIERARCHY.indexOf(role);
  const minRank = ROLE_HIERARCHY.indexOf(minRole);
  return userRank >= minRank;
}

/**
 * True when the current user is a field worker — the persona that belongs on
 * the /field shell rather than the /app engineer console. Used by the route
 * guards to send each persona to its own home.
 */
export function useIsWorker() {
  return useRole() === WORKER_ROLE;
}
