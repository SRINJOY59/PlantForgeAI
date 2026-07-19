// Route-level role guard. Wraps a page component and redirects to /app
// when the current user's role is below minRole. This covers direct URL
// access (someone typing /app/connectors in the address bar) which
// SideRail filtering alone can't prevent.
//
// Usage in App.jsx:
//   <Route path="graph" element={
//     <RoleRoute minRole="engineer"><GraphExplorer /></RoleRoute>
//   } />

import { Navigate } from "react-router-dom";
import { ROLE_HIERARCHY, useRole } from "./useRole";

export default function RoleRoute({ minRole, children, redirectTo = "/app" }) {
  const role = useRole();
  const userRank = ROLE_HIERARCHY.indexOf(role);
  const minRank = ROLE_HIERARCHY.indexOf(minRole);

  if (userRank < minRank) {
    return <Navigate to={redirectTo} replace />;
  }
  return children;
}
