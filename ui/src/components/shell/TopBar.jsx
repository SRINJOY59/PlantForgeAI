import { useNavigate } from "react-router-dom";
import { LogOut, Moon, Sun } from "lucide-react";
import { useAuth } from "../../auth/AuthProvider";
import { useTheme } from "../../lib/theme";
import FreshnessPill from "./FreshnessPill";

const UNITS = ["All units", "Unit 100", "Unit 200", "Unit 300"];

export default function TopBar() {
  const { dark, toggle } = useTheme();
  const { user, signOut, demoMode } = useAuth();
  const nav = useNavigate();

  async function handleSignOut() {
    await signOut();
    nav("/");
  }

  return (
    <header className="flex h-14 items-center gap-4 border-b border-gray-200 bg-white px-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center gap-2 font-semibold">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-steel-600 text-sm text-white">
          P
        </span>
        <span className="hidden sm:inline">PlantMind</span>
      </div>

      <select className="input h-9 w-auto py-1 text-sm">
        {UNITS.map((u) => (
          <option key={u}>{u}</option>
        ))}
      </select>

      <div className="flex-1" />

      <FreshnessPill />

      <button onClick={toggle} className="btn-ghost px-2" title="Toggle theme">
        {dark ? <Sun size={18} /> : <Moon size={18} />}
      </button>

      <div className="flex items-center gap-2 border-l border-gray-200 pl-3 dark:border-slate-800">
        <div className="hidden text-right text-xs sm:block">
          <div className="font-medium">{user?.email ?? "Demo user"}</div>
          <div className="muted">{demoMode ? "demo mode" : "signed in"}</div>
        </div>
        <button onClick={handleSignOut} className="btn-ghost px-2" title="Sign out">
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}
