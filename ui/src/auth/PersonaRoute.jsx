// The persona gate. Roles operator..admin belong on the /app engineer console;
// the worker role belongs on the /field mobile copilot. These two guards keep
// each persona on its own surface no matter where a login or a typed URL lands
// them, so the split is enforced by routing rather than by hoping the redirect
// after sign-in got it right.
//
//   <WorkerOnly>  - render for workers; send everyone else to /app
//   <ConsoleOnly> - render for operator+; send workers to /field
//
// Both wait out the auth `loading` window (via the surrounding ProtectedRoute)
// before deciding, so a worker with a hook-minted token is routed straight to
// /field without a flash of the console.

import { Navigate } from "react-router-dom";
import { useIsWorker } from "./useRole";

export function WorkerOnly({ children }) {
  return useIsWorker() ? children : <Navigate to="/app" replace />;
}

export function ConsoleOnly({ children }) {
  return useIsWorker() ? <Navigate to="/field" replace /> : children;
}
