import React, { Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import ProtectedRoute from "./auth/ProtectedRoute";
import RoleRoute from "./auth/RoleRoute";
import AppShell from "./components/shell/AppShell";

// Lightweight pages (loaded instantly)
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import SignUp from "./pages/SignUp";
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
      <Route
        path="/app"
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        {/* operator+ */}
        <Route index element={<Ask />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="profile" element={<Profile />} />
        <Route path="documents" element={<Suspended><Documents /></Suspended>} />

        {/* engineer+ */}
        <Route path="moc" element={
          <RoleRoute minRole="engineer"><Suspended><Moc /></Suspended></RoleRoute>
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

        {/* admin only */}
        <Route path="connectors" element={
          <RoleRoute minRole="admin"><Suspended><Connectors /></Suspended></RoleRoute>
        } />
      </Route>
    </Routes>
  );
}
