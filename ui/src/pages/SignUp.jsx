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
    <AuthShell title="Create your account" foot={
      <>Already have an account? <Link to="/login" className="text-steel-600">Sign in</Link></>
    }>
      <form onSubmit={submit} className="space-y-3">
        <input className="input" type="email" placeholder="Work email" value={email}
               onChange={(e) => setEmail(e.target.value)} />
        <input className="input" type="password" placeholder="Password (8+ chars)"
               value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button className="btn-primary w-full justify-center" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
    </AuthShell>
  );
}
