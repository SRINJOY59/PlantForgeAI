import { useNavigate } from "react-router-dom";
import { LogOut, ChevronDown, Moon, Sun, Menu } from "lucide-react";
import Logo from "../Logo";
import { useAuth } from "../../auth/AuthProvider";
import { useProfile } from "../../state/ProfileContext";
import { displayName, initials } from "../../lib/profile";
import { useTheme } from "../../lib/theme";
import FreshnessPill from "./FreshnessPill";
import { useEffect, useState } from "react";

const UNITS = ["All units", "Unit 100", "Unit 200", "Unit 300"];

export default function TopBar({ onMenu }) {
  const { dark, toggle } = useTheme();
  const { user, signOut, demoMode } = useAuth();
  const { profile } = useProfile();
  const nav = useNavigate();
  const [unit, setUnit] = useState("All units");

  // the unit someone owns is the unit they almost always mean, so the filter
  // starts there rather than at "All units"
  useEffect(() => {
    if (profile?.home_unit && UNITS.includes(profile.home_unit)) {
      setUnit(profile.home_unit);
    }
  }, [profile?.home_unit]);

  async function handleSignOut() {
    await signOut();
    nav("/");
  }

  return (
    <header
      className="flex h-14 flex-shrink-0 items-center gap-2 px-2 sm:gap-4 sm:px-4"
      style={{
        background: "var(--bg-panel)",
        borderBottom: "1px solid var(--border)",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
      }}
    >
      {/* Drawer toggle. Only exists below md, where the rail is not on screen. */}
      <button
        type="button"
        onClick={onMenu}
        aria-label="Open navigation"
        className="btn-ghost flex-shrink-0 px-2 py-1.5 md:hidden"
      >
        <Menu size={18} />
      </button>

      {/* Logo */}
      <div className="flex flex-shrink-0 items-center gap-2.5 select-none sm:mr-2">
        <Logo size={28} />
        <span
          className="hidden sm:block text-sm font-bold"
          style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", color: "var(--text)" }}
        >
          PlantForge<span style={{ color: "var(--brand)" }}>.ai</span>
        </span>
      </div>

      {/* Divider */}
      <div className="hidden h-6 w-px sm:block" style={{ background: "var(--border)" }} />

      {/* Unit selector. Narrows on a phone rather than disappearing - which
          unit you are looking at changes what every page means. */}
      <div className="relative min-w-0">
        <select
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          className="input h-8 w-[104px] appearance-none py-0 pl-2 pr-6 text-xs cursor-pointer sm:w-auto sm:pl-3 sm:pr-8"
          style={{ fontSize: "12px" }}
        >
          {UNITS.map((u) => <option key={u}>{u}</option>)}
        </select>
        <ChevronDown
          size={11}
          className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 sm:right-2.5"
          style={{ color: "var(--muted)" }}
        />
      </div>

      <div className="flex-1" />

      {/* Ingestion freshness is context, not an action - it yields its space to
          the controls once the bar gets tight. */}
      <div className="hidden lg:block">
        <FreshnessPill />
      </div>

      {/* Theme toggle */}
      <button onClick={toggle} className="btn-ghost flex-shrink-0 px-2 py-1.5" title="Toggle theme">
        {dark ? <Sun size={16} /> : <Moon size={16} />}
      </button>

      {/* User section */}
      <button
        onClick={() => nav("/app/profile")}
        className="flex flex-shrink-0 items-center gap-3 border-l pl-2 text-left transition-opacity hover:opacity-80 sm:pl-3"
        style={{ borderColor: "var(--border)" }}
        title="Your profile"
      >
        <div className="hidden sm:block text-right">
          <div className="text-xs font-semibold" style={{ color: "var(--text)" }}>
            {displayName(profile, user)}
          </div>
          <div
            className="text-[10px] font-medium"
            style={{ color: profile?.job_title ? "var(--muted)"
                            : demoMode ? "var(--warning)" : "var(--success)" }}
          >
            {profile?.job_title
              ? [profile.job_title, profile.home_unit].filter(Boolean).join(" · ")
              : demoMode ? "demo mode" : "● signed in"}
          </div>
        </div>

        <div
          className="grid h-7 w-7 flex-shrink-0 place-items-center rounded-full text-[10px] font-bold uppercase"
          style={{
            background: "var(--brand-light)",
            color: "var(--blue)",
            border: "1px solid var(--brand-mid)",
          }}
        >
          {initials(profile, user)}
        </div>
      </button>

      <button onClick={handleSignOut} className="btn-ghost flex-shrink-0 px-2 py-1.5" title="Sign out">
        <LogOut size={15} />
      </button>
    </header>
  );
}
