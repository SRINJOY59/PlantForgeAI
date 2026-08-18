import React, { Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import ProtectedRoute from "./auth/ProtectedRoute";
import RoleRoute from "./auth/RoleRoute";
import { ConsoleOnly, WorkerOnly } from "./auth/PersonaRoute";
import AppShell from "./components/shell/AppShell";
import FieldShell from "./components/field/FieldShell";

// Lightweight pages (loaded instantly)
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import SignUp from "./pages/SignUp";
import Dashboard from "./pages/app/Dashboard";
import Ask from "./pages/app/Ask";
import Alerts from "./pages/app/Alerts";
import Profile from "./pages/app/Profile";

// Heavy pages (lazy loaded to save bandwidth)
const Moc = React.lazy(() => import("./pages/app/Moc"));
const Documents = React.lazy(() => import("./pages/app/Documents"));
const GraphExplorer = React.lazy(() => import("./pages/app/GraphExplorer"));
const Compliance = React.lazy(() => import("./pages/app/Compliance"));
const Connectors = React.lazy(() => import("./pages/app/Connectors"));
const Interview = React.lazy(() => import("./pages/app/Interview"));
const Reports = React.lazy(() => import("./pages/app/Reports"));
const Permits = React.lazy(() => import("./pages/app/Permits"));
const WorkOrders = React.lazy(() => import("./pages/app/WorkOrders"));
const Simulation = React.lazy(() => import("./pages/app/Simulation"));
const FaultLibrary = React.lazy(() => import("./pages/app/FaultLibrary"));
const FieldCopilot = React.lazy(() => import("./pages/field/FieldCopilot"));
const FieldAsk = React.lazy(() => import("./pages/field/FieldAsk"));

const Suspended = ({ children }) => (
  <Suspense fallback={<div className="flex h-full items-center justify-center p-8 text-slate-500">Loading...</div>}>
    {children}
  </Suspense>
);

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<SignUp />} />
      {/* Field worker persona — its own mobile shell, gated so only workers
          land here and workers never reach the engineer console below. */}
      <Route
        path="/field"
        element={
          <ProtectedRoute>
            <WorkerOnly>
              <FieldShell />
            </WorkerOnly>
          </ProtectedRoute>
        }
      >
        <Route index element={<Suspended><FieldCopilot /></Suspended>} />
        <Route path="ask" element={<Suspended><FieldAsk /></Suspended>} />
      </Route>

      <Route
        path="/app"
        element={
          <ProtectedRoute>
            <ConsoleOnly>
              <AppShell />
            </ConsoleOnly>
          </ProtectedRoute>
        }
      >
        {/* operator+ */}
        <Route index element={<Dashboard />} />
        <Route path="ask" element={<Ask />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="profile" element={<Profile />} />
        <Route path="documents" element={<Suspended><Documents /></Suspended>} />

        {/* engineer+ */}
        <Route path="moc" element={
          <RoleRoute minRole="engineer"><Suspended><Moc /></Suspended></RoleRoute>
        } />
        <Route path="simulation" element={
          <RoleRoute minRole="engineer"><Suspended><Simulation /></Suspended></RoleRoute>
        } />
        <Route path="fault-library" element={
          <RoleRoute minRole="engineer"><Suspended><FaultLibrary /></Suspended></RoleRoute>
        } />
        <Route path="graph" element={
          <RoleRoute minRole="engineer"><Suspended><GraphExplorer /></Suspended></RoleRoute>
        } />
        <Route path="compliance" element={
          <RoleRoute minRole="engineer"><Suspended><Compliance /></Suspended></RoleRoute>
        } />
        <Route path="interview" element={
          <RoleRoute minRole="engineer"><Suspended><Interview /></Suspended></RoleRoute>
        } />
        <Route path="reports" element={
          <RoleRoute minRole="engineer"><Suspended><Reports /></Suspended></RoleRoute>
        } />
        <Route path="permits" element={
          <RoleRoute minRole="engineer"><Suspended><Permits /></Suspended></RoleRoute>
        } />
        <Route path="work-orders" element={
          <RoleRoute minRole="engineer"><Suspended><WorkOrders /></Suspended></RoleRoute>
        } />

        {/* admin only */}
        <Route path="connectors" element={
          <RoleRoute minRole="admin"><Suspended><Connectors /></Suspended></RoleRoute>
        } />
      </Route>
    </Routes>
  );
}
