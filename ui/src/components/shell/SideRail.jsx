import { NavLink } from "react-router-dom";
import {
  Bell, GitBranch, GitPullRequestArrow, MessageSquare, FileStack, ShieldCheck,
  Plug, Leaf, UserRound, AudioLines, Shield, LayoutDashboard,
  FilePieChart, FileSignature, Mic, Activity, Fingerprint, X,
} from "lucide-react";
import { useAlerts } from "../../state/AlertsContext";
import { ROLE_HIERARCHY, useRole } from "../../auth/useRole";
import { Wordmark } from "../Logo";

// minRole: the minimum role required to see this item.
// The hierarchy is: operator < planner < engineer < admin
const nav = [
  { to: "/app", icon: LayoutDashboard, label: "Home", minRole: "operator", end: true },
  { to: "/app/ask", icon: MessageSquare, label: "Ask", minRole: "operator" },
  { to: "/app/alerts", icon: Bell, label: "Alerts", minRole: "operator", badge: true },
  { to: "/app/documents", icon: FileStack, label: "Documents", minRole: "operator" },
  { to: "/app/moc", icon: GitPullRequestArrow, label: "Change Impact", minRole: "engineer" },
  { to: "/app/simulation", icon: Activity, label: "Simulation", minRole: "engineer" },
  { to: "/app/fault-library", icon: Fingerprint, label: "Fault Library", minRole: "engineer" },
  { to: "/app/reports", icon: FilePieChart, label: "Asset Reports", minRole: "engineer" },
  { to: "/app/permits", icon: FileSignature, label: "Permits", minRole: "engineer" },
  { to: "/app/graph", icon: GitBranch, label: "Graph", minRole: "engineer" },
  { to: "/app/compliance", icon: ShieldCheck, label: "Compliance", minRole: "engineer" },
  { to: "/app/interview", icon: AudioLines, label: "Interview", minRole: "engineer" },
  { to: "/app/connectors", icon: Plug, label: "Connectors", minRole: "admin" },
  { to: "/app/profile", icon: UserRound, label: "Profile", minRole: "operator" },
];

const ROLE_LABELS = {
  operator: { label: "Operator", color: "#64748b" },
  planner: { label: "Planner", color: "#0284c7" },
  engineer: { label: "Engineer", color: "#2563eb" },
  admin: { label: "Admin", color: "#7c3aed" },
};

// 220px of permanent rail is over half of a 375px phone, so below `md` the
// rail leaves the flow entirely and slides in over the page as a drawer.
// `open`/`onClose` are ignored at md and up, where it is a static column again.
export default function SideRail({ open = false, onClose = () => {} }) {
  const { unread } = useAlerts();
  const role = useRole();
  const userRank = ROLE_HIERARCHY.indexOf(role);

  // Only show items the current user's role can access
  const visibleNav = nav.filter(
    (item) => userRank >= ROLE_HIERARCHY.indexOf(item.minRole)
  );

  const roleInfo = ROLE_LABELS[role] ?? ROLE_LABELS.operator;

  return (
    <>
      {/* Scrim. Only rendered while the drawer is open, and only below md -
          tapping anywhere off the rail is the fastest way to dismiss it. */}
      {open && (
        <button
          type="button"
          aria-label="Close navigation"
          onClick={onClose}
          className="fixed inset-0 z-30 md:hidden"
          style={{ background: "rgba(15, 23, 42, 0.45)" }}
        />
      )}

      <nav
        className={`flex flex-col gap-0.5 py-3 fixed inset-y-0 left-0 z-40
                    transition-transform duration-200 ease-out
                    md:static md:z-auto md:translate-x-0 md:transition-none
                    ${open ? "translate-x-0" : "-translate-x-full"}`}
        style={{
          width: "220px",
          minWidth: "220px",
          background: "var(--bg-panel)",
          borderRight: "1px solid var(--border)",
        }}
      >
        {/* Logo. The drawer covers the TopBar (and its menu button) on mobile,
            so it carries its own dismiss control. */}
        <div
          className="flex items-center justify-between px-4 pb-3 mb-1"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <Wordmark size={28} className="text-sm" />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="btn-ghost -mr-1 p-1 md:hidden"
          >
            <X size={16} />
          </button>
        </div>

      {/* Nav items. min-h-0 + overflow so a long list still scrolls on a short
          phone instead of pushing the role badge off the bottom. */}
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pt-1">
        {visibleNav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={onClose}
            className="group flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150 mb-0.5"
            style={({ isActive }) => ({
              background: isActive ? "var(--brand-light)" : "transparent",
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
          PlantForge.ai v2.0
        </span>
        </div>
      </nav>
    </>
  );
}
