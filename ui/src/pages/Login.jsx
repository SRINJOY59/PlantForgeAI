import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { supabase, supabaseEnabled } from "../lib/supabase";

export default function Login() {
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
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) setError(error.message);
    else nav("/app");
  }

  return (
    <AuthShell title="Sign in to PlantMind" foot={
      <>New here? <Link to="/signup" className="text-steel-600">Create an account</Link></>
    }>
      {!supabaseEnabled && (
        <p className="mb-4 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
          Supabase not configured — continuing in demo mode.
        </p>
      )}
      <form onSubmit={submit} className="space-y-3">
        <input className="input" type="email" placeholder="Email" value={email}
               onChange={(e) => setEmail(e.target.value)} />
        <input className="input" type="password" placeholder="Password"
               value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button className="btn-primary w-full justify-center" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthShell>
  );
}

export function AuthShell({ title, children, foot }) {
  return (
    <div className="grid min-h-full place-items-center bg-gray-50 px-6 dark:bg-slate-950">
      <div className="w-full max-w-sm">
        <Link to="/" className="mb-6 flex items-center justify-center gap-2 font-semibold">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-steel-600 text-white">P</span>
          PlantMind
        </Link>
        <div className="surface rounded-xl p-6">
          <h1 className="mb-5 text-lg font-semibold">{title}</h1>
          {children}
        </div>
        <p className="mt-4 text-center text-sm muted">{foot}</p>
      </div>
    </div>
  );
}
