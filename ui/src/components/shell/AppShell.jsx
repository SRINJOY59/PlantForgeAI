import { Outlet } from "react-router-dom";
import SideRail from "./SideRail";
import TopBar from "./TopBar";
import { AlertsProvider } from "../../state/AlertsContext";

export default function AppShell() {
  return (
    <AlertsProvider>
      <div className="flex h-screen flex-col" style={{ background: "var(--bg-base)" }}>
        <TopBar />
        <div className="accent-line flex-shrink-0" />
        <div className="flex min-h-0 flex-1">
          <SideRail />
          <main className="min-h-0 flex-1 overflow-hidden">
            <Outlet />
          </main>
        </div>
      </div>
    </AlertsProvider>
  );
}
