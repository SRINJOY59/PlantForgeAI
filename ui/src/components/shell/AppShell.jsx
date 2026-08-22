import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import SideRail from "./SideRail";
import TopBar from "./TopBar";
import { AlertsProvider } from "../../state/AlertsContext";
import { ProfileProvider } from "../../state/ProfileContext";

export default function AppShell() {
  // Only meaningful below md, where the rail is an overlay drawer rather than
  // a column. Lives here because both TopBar (the button) and SideRail (the
  // panel) need it and they are siblings.
  const [navOpen, setNavOpen] = useState(false);
  const { pathname } = useLocation();

  // Navigating from inside the drawer has to close it, or the page you just
  // asked for renders behind an open menu.
  useEffect(() => setNavOpen(false), [pathname]);

  return (
    <ProfileProvider>
      <AlertsProvider>
        <div className="flex h-screen flex-col" style={{ background: "var(--bg-base)" }}>
          <TopBar onMenu={() => setNavOpen((v) => !v)} />
          <div className="accent-line flex-shrink-0" />
          <div className="flex min-h-0 flex-1">
            <SideRail open={navOpen} onClose={() => setNavOpen(false)} />
            {/* min-w-0: without it a wide child (a table, a canvas) sets the
                flex item's floor to its own content width and the whole page
                scrolls sideways instead of the child scrolling inside it. */}
            <main className="min-h-0 min-w-0 flex-1 overflow-hidden">
              <Outlet />
            </main>
          </div>
        </div>
      </AlertsProvider>
    </ProfileProvider>
  );
}
