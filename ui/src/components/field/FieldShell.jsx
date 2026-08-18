// The worker persona's shell — deliberately not the engineer AppShell. Built
// mobile-first for a phone held one-handed at the equipment: a single top bar
// (identity + language + sign-out), then the copilot fills the rest. No side
// rail, no dense nav — a field worker has one tool, and this is it.
//
// Language lives here, at the top of the persona, and is handed to the copilot
// through the router outlet context: it drives both the model's answer language
// and the speech engine's voice, so it belongs above the one screen that uses
// it. The choice is remembered across sessions.

import { useEffect, useState } from "react";
import { NavLink, Outlet, useOutletContext } from "react-router-dom";
import { Globe, LogOut, HardHat, Gauge, MessageSquare } from "lucide-react";
import { useAuth } from "../../auth/AuthProvider";
import { LANGUAGES, t } from "../../lib/i18n";

const LANG_KEY = "plantmind.field.lang";

export default function FieldShell() {
  const { signOut } = useAuth();
  const [lang, setLang] = useState(() => {
    try { return localStorage.getItem(LANG_KEY) || "en"; } catch { return "en"; }
  });

  useEffect(() => {
    try { localStorage.setItem(LANG_KEY, lang); } catch { /* private mode */ }
  }, [lang]);

  return (
    <div className="flex h-full flex-col" style={{ background: "var(--bg-surface)" }}>
      <header
        className="flex flex-shrink-0 items-center gap-3 px-4 py-3"
        style={{ background: "var(--bg-panel)", borderBottom: "1px solid var(--border)" }}
      >
        <div
          className="grid h-9 w-9 flex-shrink-0 place-items-center rounded-xl"
          style={{ background: "var(--brand-light)", border: "1px solid var(--brand-mid)" }}
        >
          <HardHat size={18} style={{ color: "var(--blue)" }} />
        </div>
        <div className="min-w-0 flex-1">
          <h1
            className="truncate text-sm font-bold leading-tight"
            style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", color: "var(--text)" }}
          >
            {t("title", lang)}
          </h1>
        </div>

        {/* Language selector — the whole point of the multilingual persona, so
            it sits in the bar, always one tap away. */}
        <label className="relative flex items-center">
          <Globe size={15} style={{ color: "var(--muted)" }} className="pointer-events-none absolute left-2.5" />
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            aria-label={t("language", lang)}
            className="appearance-none rounded-lg py-1.5 pl-8 pr-3 text-sm outline-none"
            style={{ background: "var(--bg-surface)", border: "1px solid var(--border-md)", color: "var(--text)" }}
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>{l.label}</option>
            ))}
          </select>
        </label>

        <button
          onClick={signOut}
          aria-label={t("sign_out", lang)}
          className="btn-ghost grid h-9 w-9 place-items-center rounded-lg"
        >
          <LogOut size={16} />
        </button>
      </header>

      <main className="min-h-0 flex-1">
        <Outlet context={{ lang, setLang }} />
      </main>

      {/* Bottom tabs — Copilot (asset-scoped) and Ask (general Q&A). Large,
          thumb-reachable targets for a phone held one-handed. */}
      <nav className="flex flex-shrink-0"
        style={{ background: "var(--bg-panel)", borderTop: "1px solid var(--border)" }}>
        <FieldTab to="/field" end icon={Gauge} label={t("tab_copilot", lang)} />
        <FieldTab to="/field/ask" icon={MessageSquare} label={t("tab_ask", lang)} />
      </nav>
    </div>
  );
}

function FieldTab({ to, end, icon: Icon, label }) {
  return (
    <NavLink to={to} end={end}
      className="flex flex-1 flex-col items-center gap-1 py-2.5"
      style={({ isActive }) => ({
        color: isActive ? "var(--blue)" : "var(--muted)",
        borderTop: isActive ? "2px solid var(--blue)" : "2px solid transparent",
        marginTop: "-1px",
      })}>
      <Icon size={20} />
      <span className="max-w-full truncate px-2 text-[11px] font-medium">{label}</span>
    </NavLink>
  );
}

// Convenience hook so the copilot page can read the shell's language.
export function useFieldLang() {
  return useOutletContext();
}
