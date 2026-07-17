import { useNavigate } from "react-router-dom";
import { LogOut, Leaf, ChevronDown, Moon, Sun } from "lucide-react";
import { useAuth } from "../../auth/AuthProvider";
import { useProfile } from "../../state/ProfileContext";
import { displayName, initials } from "../../lib/profile";
import { useTheme } from "../../lib/theme";
import FreshnessPill from "./FreshnessPill";
import { useEffect, useState } from "react";

const UNITS = ["All units", "Unit 100", "Unit 200", "Unit 300"];

export default function TopBar() {
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
      className="flex h-14 flex-shrink-0 items-center gap-4 px-4"
      style={{
        background: "var(--bg-panel)",
        borderBottom: "1px solid var(--border)",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 mr-2 select-none">
        <div
          className="grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg"
          style={{ background: "var(--blue)", boxShadow: "0 2px 8px rgba(37,99,235,0.25)" }}
        >
          <Leaf size={14} className="text-white" />
        </div>
        <span
          className="hidden sm:block text-sm font-bold"
          style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", color: "var(--text)" }}
        >
          PlantMind
        </span>
      </div>

      {/* Divider */}
      <div className="h-6 w-px" style={{ background: "var(--border)" }} />

      {/* Unit selector */}
      <div className="relative">
        <select
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          className="input h-8 appearance-none py-0 pl-3 pr-8 text-xs cursor-pointer"
          style={{ minWidth: "130px", fontSize: "12px" }}
        >
          {UNITS.map((u) => <option key={u}>{u}</option>)}
        </select>
        <ChevronDown
          size={11}
          className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2"
          style={{ color: "var(--muted)" }}
        />
      </div>

      <div className="flex-1" />

      <FreshnessPill />

      {/* Theme toggle */}
      <button onClick={toggle} className="btn-ghost px-2 py-1.5" title="Toggle theme">
        {dark ? <Sun size={16} /> : <Moon size={16} />}
      </button>

      {/* User section */}
      <button
        onClick={() => nav("/app/profile")}
        className="flex items-center gap-3 border-l pl-3 text-left transition-opacity hover:opacity-80"
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
            background: "#dbeafe",
            color: "var(--blue)",
            border: "1px solid #bfdbfe",
          }}
        >
          {initials(profile, user)}
        </div>
      </button>

      <button onClick={handleSignOut} className="btn-ghost px-2 py-1.5" title="Sign out">
        <LogOut size={15} />
      </button>
    </header>
  );
}
