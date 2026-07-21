import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { supabase, supabaseEnabled } from "../lib/supabase";
import { Eye, EyeOff } from "lucide-react";
import { Wordmark } from "../components/Logo";

export default function Login() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!supabaseEnabled) return nav("/app");
    setBusy(true); setError("");
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) setError(error.message);
    else nav("/app");
  }

  return (
    <AuthShell title="Sign in" subtitle="Access your plant's knowledge graph"
      foot={<>New here? <Link to="/signup" style={{ color: "var(--blue)" }}>Create an account</Link></>}
    >
      {!supabaseEnabled && (
        <div
          className="mb-4 rounded-lg px-4 py-3 text-xs"
          style={{ background: "#fef3c7", border: "1px solid #fde68a", color: "#92400e" }}
        >
          ⚡ Supabase not configured — continuing in demo mode.
        </div>
      )}
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="mb-1.5 block text-xs font-semibold" style={{ color: "var(--text-md)" }}>Email address</label>
          <input className="input" type="email" placeholder="engineer@plant.com"
            value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-semibold" style={{ color: "var(--text-md)" }}>Password</label>
          <div className="relative">
            <input className="input pr-10" type={showPwd ? "text" : "password"}
              placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} />
            <button type="button" onClick={() => setShowPwd(v => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2" style={{ color: "var(--muted)" }}>
              {showPwd ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
        </div>
        {error && (
          <p className="rounded-lg px-3 py-2 text-xs"
            style={{ background: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" }}>
            {error}
          </p>
        )}
        <button className="btn-primary w-full justify-center py-2.5 mt-2" disabled={busy}>
          {busy
            ? <span className="flex items-center gap-2">
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                Signing in…
              </span>
            : "Sign in"
          }
        </button>
      </form>
    </AuthShell>
  );
}

export function AuthShell({ title, subtitle, children, foot }) {
  return (
    <div
      className="grid min-h-full place-items-center px-6"
      style={{ background: "#f0f4f8" }}
    >
      <div className="w-full max-w-sm animate-slide-up">
        {/* Logo */}
        <Link to="/" className="mb-8 flex items-center justify-center gap-2.5">
          <Wordmark size={38} className="text-xl" />
        </Link>

        {/* Card */}
        <div
          className="rounded-2xl p-8"
          style={{
            background: "var(--bg-panel)",
            border: "1px solid var(--border)",
            boxShadow: "0 4px 24px rgba(0,0,0,0.06), 0 1px 4px rgba(0,0,0,0.04)",
          }}
        >
          <h1
            className="text-xl font-bold mb-1"
            style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", color: "var(--text)" }}
          >
            {title}
          </h1>
          {subtitle && <p className="text-sm mb-6" style={{ color: "var(--muted)" }}>{subtitle}</p>}
          {children}
        </div>

        <p className="mt-5 text-center text-sm" style={{ color: "var(--muted)" }}>{foot}</p>
      </div>
    </div>
  );
}
