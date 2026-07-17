import { useEffect, useState } from "react";
import { BadgeCheck, Building2, Check, MapPin, Save, Wrench } from "lucide-react";
import { useAuth } from "../../auth/AuthProvider";
import { useProfile } from "../../state/ProfileContext";
import {
  DEPARTMENTS, JOB_TITLES, UNITS, displayName, initials,
} from "../../lib/profile";

const BLANK = {
  full_name: "", employee_id: "", job_title: "", department: "",
  plant: "", home_unit: "", projects: [], expertise: [],
};

export default function Profile() {
  const { user, demoMode } = useAuth();
  const { profile, loading, update } = useProfile();
  const [form, setForm] = useState(BLANK);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (profile) setForm({ ...BLANK, ...profile });
  }, [profile]);

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
    setSaved(false);
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { id, updated_at, ...patch } = form;
      await update(patch);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="grid h-full place-items-center text-sm" style={{ color: "var(--muted)" }}>
        Loading profile…
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto" style={{ background: "var(--bg-surface)" }}>
      <div className="mx-auto max-w-3xl px-6 py-8">
        <Header profile={profile} user={user} />

        {demoMode && (
          <p className="mb-5 rounded-lg px-3 py-2 text-xs"
            style={{ background: "rgba(217,119,6,0.08)", color: "var(--warning)",
                     border: "1px solid rgba(217,119,6,0.2)" }}>
            Demo mode — Supabase isn't configured, so edits won't be saved.
          </p>
        )}

        <form onSubmit={submit} className="space-y-5">
          <Section title="Identity" icon={BadgeCheck}>
            <Field label="Full name">
              <input className="input" value={form.full_name ?? ""}
                placeholder="Srinjoy Das"
                onChange={(e) => set("full_name", e.target.value)} />
            </Field>
            <Field label="Employee ID">
              <input className="input" value={form.employee_id ?? ""}
                placeholder="EMP-4417"
                onChange={(e) => set("employee_id", e.target.value)} />
            </Field>
            <Field label="Work email">
              <input className="input" value={user?.email ?? "demo@local"} disabled
                style={{ opacity: 0.6, cursor: "not-allowed" }} />
            </Field>
          </Section>

          <Section title="Role" icon={Building2}>
            <Field label="Job title">
              <Picker value={form.job_title} options={JOB_TITLES}
                placeholder="Select or type a title"
                onChange={(v) => set("job_title", v)} />
            </Field>
            <Field label="Department">
              <Picker value={form.department} options={DEPARTMENTS}
                placeholder="Select or type a department"
                onChange={(v) => set("department", v)} />
            </Field>
          </Section>

          <Section title="Where you work" icon={MapPin}>
            <Field label="Plant / site">
              <input className="input" value={form.plant ?? ""}
                placeholder="Haldia Refinery"
                onChange={(e) => set("plant", e.target.value)} />
            </Field>
            <Field label="Home unit"
              hint="Sets your default filter across the app">
              <Picker value={form.home_unit} options={UNITS}
                placeholder="Select a unit"
                onChange={(v) => set("home_unit", v)} />
            </Field>
          </Section>

          <Section title="What you work on" icon={Wrench}>
            <Field label="Current projects"
              hint="One per line — the work you're accountable for right now">
              <Lines value={form.projects} placeholder={"P-101 seal reliability\nUnit 200 turnaround 2026"}
                onChange={(v) => set("projects", v)} />
            </Field>
            <Field label="Areas of expertise"
              hint="Equipment and disciplines you own">
              <Lines value={form.expertise} placeholder={"Rotating equipment\nVibration analysis"}
                onChange={(v) => set("expertise", v)} />
            </Field>
          </Section>

          {error && (
            <p className="rounded-lg px-3 py-2 text-xs"
              style={{ background: "rgba(220,38,38,0.08)", color: "var(--danger)",
                       border: "1px solid rgba(220,38,38,0.2)" }}>
              {error}
            </p>
          )}

          <div className="flex items-center gap-3 pb-8">
            <button type="submit" className="btn-primary px-4 py-2 text-xs" disabled={busy}>
              {busy
                ? <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                : <><Save size={13} /> Save profile</>}
            </button>
            {saved && (
              <span className="flex items-center gap-1.5 text-xs font-medium"
                style={{ color: "var(--success)" }}>
                <Check size={13} /> Saved
              </span>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}

function Header({ profile, user }) {
  const role = [profile?.job_title, profile?.department].filter(Boolean).join(" · ");
  const where = [profile?.plant, profile?.home_unit].filter(Boolean).join(" · ");
  return (
    <div className="mb-6 flex items-center gap-4">
      <div className="grid h-14 w-14 flex-shrink-0 place-items-center rounded-2xl text-base font-bold"
        style={{ background: "#dbeafe", color: "var(--blue)", border: "1px solid #bfdbfe" }}>
        {initials(profile, user)}
      </div>
      <div className="min-w-0">
        <h1 className="text-xl font-bold"
          style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", color: "var(--text)" }}>
          {displayName(profile, user)}
        </h1>
        <p className="truncate text-xs" style={{ color: "var(--muted)" }}>
          {role || "Add your role below"}{where ? ` — ${where}` : ""}
        </p>
      </div>
    </div>
  );
}

function Section({ title, icon: Icon, children }) {
  return (
    <section className="rounded-xl p-5"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)",
               boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
      <div className="mb-4 flex items-center gap-2">
        <Icon size={14} style={{ color: "var(--blue)" }} />
        <h2 className="text-[10px] font-semibold uppercase tracking-widest"
          style={{ color: "var(--muted)" }}>
          {title}
        </h2>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </section>
  );
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium" style={{ color: "var(--text-md)" }}>
        {label}
      </label>
      {children}
      {hint && (
        <p className="mt-1 text-[10px]" style={{ color: "var(--muted-lt)" }}>{hint}</p>
      )}
    </div>
  );
}

// A select would force one of our guesses; a plain input would lose the
// vocabulary. datalist keeps the list as a suggestion and lets a plant use
// its own titles.
function Picker({ value, options, placeholder, onChange }) {
  const id = `list-${placeholder?.replace(/\W/g, "")}`;
  return (
    <>
      <input className="input" list={id} value={value ?? ""} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)} />
      <datalist id={id}>
        {options.map((o) => <option key={o} value={o} />)}
      </datalist>
    </>
  );
}

// text[] in postgres, one-per-line in the box
function Lines({ value, placeholder, onChange }) {
  return (
    <textarea
      className="input resize-y"
      rows={3}
      placeholder={placeholder}
      value={(value ?? []).join("\n")}
      onChange={(e) =>
        onChange(e.target.value.split("\n").map((l) => l.trim()).filter(Boolean))
      }
    />
  );
}
