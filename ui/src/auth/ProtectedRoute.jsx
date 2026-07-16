import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthProvider";

export default function ProtectedRoute({ children }) {
  const { user, loading, demoMode } = useAuth();

  if (loading) {
    return (
      <div className="grid h-full place-items-center muted text-sm">
        Loading…
      </div>
    );
  }
  // Without Supabase configured, the app is open (demo mode)
  if (!demoMode && !user) return <Navigate to="/login" replace />;
  return children;
}
