import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Eye, EyeOff, MailCheck } from "lucide-react";
import { supabase, supabaseEnabled } from "../lib/supabase";
import { DEPARTMENTS, JOB_TITLES, UNITS } from "../lib/profile";
import { AuthShell } from "./Login";

// Two steps rather than one long form: credentials, then who you are. It all
// goes up in a single signUp call - supabase carries the second step in the
// user's metadata, and the handle_new_user trigger copies it into profiles, so
// the profile exists the moment the account does. Nobody lands on an empty one.
export default function SignUp() {
  const nav = useNavigate();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    full_name: "", email: "", password: "",
    job_title: "", department: "", plant: "", home_unit: "",
  });
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmSent, setConfirmSent] = useState(false);

  const set = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
    setError("");
  };

  function next(e) {
    e.preventDefault();
    if (!form.full_name.trim()) return setError("Your name, please.");
    if (!/^\S+@\S+\.\S+$/.test(form.email)) return setError("That email doesn't look right.");
    if (form.password.length < 8) return setError("Password needs at least 8 characters.");
    setError("");
    setStep(2);
  }

  async function submit(e) {
    e.preventDefault();
    if (!supabaseEnabled) return nav("/app");
    setBusy(true);
    setError("");

    const { email, password, ...profile } = form;
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: profile },      // -> raw_user_meta_data -> profiles
    });
    setBusy(false);

    if (error) return setError(error.message);
    // with email confirmation on, signUp succeeds but returns no session -
    // navigating would just bounce off ProtectedRoute with no explanation
    if (!data.session) return setConfirmSent(true);
    nav("/app");
  }

  if (confirmSent) {
    return (
      <AuthShell title="Check your email"
        subtitle="One more step before you're in"
        foot={<Link to="/login" style={{ color: "var(--blue)" }}>Back to sign in</Link>}>
        <div className="flex flex-col items-center py-4 text-center">
          <div className="mb-4 grid h-12 w-12 place-items-center rounded-xl"
            style={{ background: "var(--brand-light)", border: "1px solid var(--brand-mid)" }}>
            <MailCheck size={20} style={{ color: "var(--blue)" }} />
          </div>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-md)" }}>
            We sent a confirmation link to <strong>{form.email}</strong>.
            Open it, then sign in.
          </p>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title={step === 1 ? "Create your account" : "About you"}
      subtitle={step === 1
        ? "Start building your plant's knowledge graph"
        : "So the brain knows whose questions it's answering"}
      foot={step === 1
        ? <>Already have an account? <Link to="/login" style={{ color: "var(--blue)" }}>Sign in</Link></>
        : null}
    >
      <Steps step={step} />

      {!supabaseEnabled && (
        <div className="mb-4 rounded-lg px-4 py-3 text-xs"
          style={{ background: "#fef3c7", border: "1px solid #fde68a", color: "#92400e" }}>
          ⚡ Supabase not configured — continuing in demo mode.
        </div>
      )}

      <form onSubmit={step === 1 ? next : submit} className="space-y-4">
        {step === 1 ? (
          <>
            <Field label="Full name">
              <input className="input" placeholder="Srinjoy Das"
                value={form.full_name} onChange={set("full_name")} />
            </Field>
            <Field label="Work email">
              <input className="input" type="email" placeholder="engineer@plant.com"
                value={form.email} onChange={set("email")} />
            </Field>
            <Field label="Password" hint="At least 8 characters">
              <div className="relative">
                <input className="input pr-10" type={showPwd ? "text" : "password"}
                  placeholder="••••••••" value={form.password} onChange={set("password")} />
                <button type="button" onClick={() => setShowPwd((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  style={{ color: "var(--muted)" }}>
                  {showPwd ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </Field>
          </>
        ) : (
          <>
            <Field label="Job title">
              <Suggest value={form.job_title} onChange={set("job_title")}
                options={JOB_TITLES} placeholder="Reliability Engineer" name="titles" />
            </Field>
            <Field label="Department">
              <Suggest value={form.department} onChange={set("department")}
                options={DEPARTMENTS} placeholder="Maintenance" name="depts" />
            </Field>
            <Field label="Plant / site">
              <input className="input" placeholder="Haldia Refinery"
                value={form.plant} onChange={set("plant")} />
            </Field>
            <Field label="Home unit" hint="Your default filter across the app — you can change it later">
              <Suggest value={form.home_unit} onChange={set("home_unit")}
                options={UNITS} placeholder="Unit 200" name="units" />
            </Field>
          </>
        )}

        {error && (
          <p className="rounded-lg px-3 py-2 text-xs"
            style={{ background: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" }}>
            {error}
          </p>
        )}

        <div className="flex gap-2 pt-1">
          {step === 2 && (
            <button type="button" onClick={() => setStep(1)}
              className="btn-ghost px-3 py-2.5 text-xs" disabled={busy}>
              <ArrowLeft size={13} /> Back
            </button>
          )}
          <button className="btn-primary flex-1 justify-center py-2.5" disabled={busy}>
            {busy ? (
              <span className="flex items-center gap-2">
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                Creating account…
              </span>
            ) : step === 1 ? "Continue" : "Create account"}
          </button>
        </div>
      </form>
    </AuthShell>
  );
}

function Steps({ step }) {
  return (
    <div className="mb-5 flex items-center gap-2">
      {[1, 2].map((n) => (
        <div key={n} className="h-1 flex-1 rounded-full transition-colors duration-200"
          style={{ background: n <= step ? "var(--blue)" : "var(--border-md)" }} />
      ))}
      <span className="ml-1 text-[10px] font-medium" style={{ color: "var(--muted)" }}>
        {step} / 2
      </span>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold" style={{ color: "var(--text-md)" }}>
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-[10px]" style={{ color: "var(--muted-lt)" }}>{hint}</p>}
    </div>
  );
}

// suggestions, not a fixed list: every plant names its roles differently
function Suggest({ value, onChange, options, placeholder, name }) {
  return (
    <>
      <input className="input" list={name} value={value} onChange={onChange}
        placeholder={placeholder} />
      <datalist id={name}>
        {options.map((o) => <option key={o} value={o} />)}
      </datalist>
    </>
  );
}
