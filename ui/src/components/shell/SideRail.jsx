import { NavLink } from "react-router-dom";
import {
  Bell, GitBranch, MessageSquare, FileStack, ShieldCheck, Plug,
} from "lucide-react";
import { useAlerts } from "../../state/AlertsContext";

const nav = [
  { to: "/app", icon: MessageSquare, label: "Ask", end: true },
  { to: "/app/alerts", icon: Bell, label: "Alerts", badge: true },
  { to: "/app/graph", icon: GitBranch, label: "Graph" },
  { to: "/app/documents", icon: FileStack, label: "Documents" },
  { to: "/app/compliance", icon: ShieldCheck, label: "Compliance" },
  { to: "/app/connectors", icon: Plug, label: "Connectors" },
];

export default function SideRail() {
  const { unread } = useAlerts();
  return (
    <nav className="flex w-16 flex-col items-center gap-1 border-r border-gray-200 bg-white py-3 dark:border-slate-800 dark:bg-slate-900 sm:w-52 sm:items-stretch sm:px-3">
      {nav.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            `group flex items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium transition-colors ${
              isActive
                ? "bg-steel-50 text-steel-700 dark:bg-steel-950 dark:text-steel-200"
                : "text-gray-600 hover:bg-gray-100 dark:text-slate-400 dark:hover:bg-slate-800"
            }`
          }
        >
          <span className="relative">
            <item.icon size={18} />
            {item.badge && unread > 0 && (
              <span className="absolute -right-1.5 -top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
                {unread}
              </span>
            )}
          </span>
          <span className="hidden sm:inline">{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
