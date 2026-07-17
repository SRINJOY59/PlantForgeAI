import { NavLink } from "react-router-dom";
import {
  Bell, GitBranch, GitPullRequestArrow, MessageSquare, FileStack, ShieldCheck,
  Plug, Leaf, UserRound,
} from "lucide-react";
import { useAlerts } from "../../state/AlertsContext";

const nav = [
  { to: "/app",            icon: MessageSquare, label: "Ask",        end: true  },
  { to: "/app/alerts",     icon: Bell,          label: "Alerts",     badge: true },
  { to: "/app/moc",        icon: GitPullRequestArrow, label: "Change Impact" },
  { to: "/app/graph",      icon: GitBranch,     label: "Graph"       },
  { to: "/app/documents",  icon: FileStack,     label: "Documents"   },
  { to: "/app/compliance", icon: ShieldCheck,   label: "Compliance"  },
  { to: "/app/connectors", icon: Plug,          label: "Connectors"  },
  { to: "/app/profile",    icon: UserRound,     label: "Profile"     },
];

export default function SideRail() {
  const { unread } = useAlerts();

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
        {nav.map((item) => (
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

      {/* Bottom version */}
      <div className="px-4 pb-3 pt-2" style={{ borderTop: "1px solid var(--border)" }}>
        <span className="text-[11px] font-mono" style={{ color: "var(--muted-lt)" }}>
          PlantMind v2.0
        </span>
      </div>
    </nav>
  );
}
