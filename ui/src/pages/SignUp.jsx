import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { supabase, supabaseEnabled } from "../lib/supabase";
import { AuthShell } from "./Login";

export default function SignUp() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!supabaseEnabled) return nav("/app");
    setBusy(true);
    setError("");
    const { error } = await supabase.auth.signUp({ email, password });
    setBusy(false);
    if (error) setError(error.message);
    else nav("/app");
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Start building your plant's knowledge graph"
      foot={
        <>Already have an account? <Link to="/login" style={{ color: "#00ccf5" }}>Sign in</Link></>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="mb-1.5 block text-xs font-medium" style={{ color: "#64748b" }}>
            Work email
          </label>
          <input
            className="input"
            type="email"
            placeholder="engineer@plant.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium" style={{ color: "#64748b" }}>
            Password <span style={{ color: "#334155" }}>(8+ characters)</span>
          </label>
          <input
            className="input"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && (
          <p
            className="rounded-lg px-3 py-2 text-xs"
            style={{ background: "rgba(255,61,110,0.08)", color: "#ff3d6e", border: "1px solid rgba(255,61,110,0.2)" }}
          >
            {error}
          </p>
        )}
        <button
          className="btn-primary w-full justify-center py-2.5 mt-2"
          disabled={busy}
        >
          {busy ? (
            <span className="flex items-center gap-2">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              Creating account…
            </span>
          ) : "Create account"}
        </button>
      </form>
    </AuthShell>
  );
}
