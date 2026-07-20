import { NavLink } from "react-router-dom";
import {
  Bell, GitBranch, GitPullRequestArrow, MessageSquare, FileStack, ShieldCheck,
  Plug, Leaf, UserRound, AudioLines, Shield, LayoutDashboard,
  FilePieChart, FileSignature, Mic,
} from "lucide-react";
import { useAlerts } from "../../state/AlertsContext";
import { ROLE_HIERARCHY, useRole } from "../../auth/useRole";

// minRole: the minimum role required to see this item.
// The hierarchy is: operator < planner < engineer < admin
const nav = [
  { to: "/app",            icon: LayoutDashboard,    label: "Home",          minRole: "operator", end: true  },
  { to: "/app/ask",        icon: MessageSquare,      label: "Ask",           minRole: "operator" },
  { to: "/app/copilot",    icon: Mic,                label: "Field Copilot", minRole: "operator" },
  { to: "/app/alerts",     icon: Bell,               label: "Alerts",        minRole: "operator", badge: true },
  { to: "/app/documents",  icon: FileStack,           label: "Documents",     minRole: "operator" },
  { to: "/app/moc",        icon: GitPullRequestArrow, label: "Change Impact", minRole: "engineer" },
  { to: "/app/reports",    icon: FilePieChart,       label: "Asset Reports", minRole: "engineer" },
  { to: "/app/permits",    icon: FileSignature,      label: "Permits",       minRole: "engineer" },
  { to: "/app/graph",      icon: GitBranch,           label: "Graph",         minRole: "engineer" },
  { to: "/app/compliance", icon: ShieldCheck,         label: "Compliance",    minRole: "engineer" },
  { to: "/app/interview",  icon: AudioLines,          label: "Interview",     minRole: "engineer" },
  { to: "/app/connectors", icon: Plug,                label: "Connectors",    minRole: "admin"    },
  { to: "/app/profile",    icon: UserRound,           label: "Profile",       minRole: "operator" },
];

const ROLE_LABELS = {
  operator: { label: "Operator",  color: "#64748b" },
  planner:  { label: "Planner",   color: "#0284c7" },
  engineer: { label: "Engineer",  color: "#2563eb" },
  admin:    { label: "Admin",     color: "#7c3aed" },
};

export default function SideRail() {
  const { unread } = useAlerts();
  const role = useRole();
  const userRank = ROLE_HIERARCHY.indexOf(role);

  // Only show items the current user's role can access
  const visibleNav = nav.filter(
    (item) => userRank >= ROLE_HIERARCHY.indexOf(item.minRole)
  );

  const roleInfo = ROLE_LABELS[role] ?? ROLE_LABELS.operator;

  return (
    <nav
      className="flex flex-col gap-0.5 py-3"
      style={{
        width: "220px",
        minWidth: "220px",
        background: "var(--bg-panel)",
        borderRight: "1px solid var(--border)",
      }}
    >
      {/* Logo */}
      <div
        className="flex items-center gap-2.5 px-4 pb-3 mb-1"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div
          className="grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg"
          style={{ background: "var(--blue)", boxShadow: "0 2px 8px rgba(37,99,235,0.3)" }}
        >
          <Leaf size={15} className="text-white" />
        </div>
        <span
          className="font-bold text-sm tracking-tight"
          style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", color: "#1e293b" }}
        >
          PlantMind
        </span>
      </div>

      {/* Nav items */}
      <div className="flex-1 px-2 pt-1">
        {visibleNav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className="group flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150 mb-0.5"
            style={({ isActive }) => ({
              background: isActive ? "#eff6ff" : "transparent",
              color: isActive ? "var(--blue)" : "var(--muted)",
              borderLeft: isActive ? "3px solid var(--blue)" : "3px solid transparent",
            })}
          >
            {({ isActive }) => (
              <>
                <span className="relative flex-shrink-0">
                  <item.icon size={16} style={{ color: isActive ? "var(--blue)" : "var(--muted-lt)" }} />
                  {item.badge && unread > 0 && (
                    <span
                      className="absolute -right-2 -top-2 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[9px] font-bold text-white"
                      style={{ background: "#dc2626" }}
                    >
                      {unread}
                    </span>
                  )}
                </span>
                <span style={{ color: isActive ? "var(--blue)" : "var(--text-md)" }}>
                  {item.label}
                </span>
              </>
            )}
          </NavLink>
        ))}
      </div>

      {/* Bottom: role badge + version */}
      <div className="px-4 pb-3 pt-2 space-y-1.5" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="flex items-center gap-1.5">
          <Shield size={10} style={{ color: roleInfo.color }} />
          <span
            className="text-[10px] font-semibold uppercase tracking-wider"
            style={{ color: roleInfo.color }}
          >
            {roleInfo.label}
          </span>
        </div>
        <span className="text-[11px] font-mono" style={{ color: "var(--muted-lt)" }}>
          PlantMind v2.0
        </span>
      </div>
    </nav>
  );
}
