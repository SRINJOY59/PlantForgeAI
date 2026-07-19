import { Route, Routes } from "react-router-dom";
import ProtectedRoute from "./auth/ProtectedRoute";
import RoleRoute from "./auth/RoleRoute";
import AppShell from "./components/shell/AppShell";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import SignUp from "./pages/SignUp";
import Ask from "./pages/app/Ask";
import Alerts from "./pages/app/Alerts";
import Moc from "./pages/app/Moc";
import Documents from "./pages/app/Documents";
import GraphExplorer from "./pages/app/GraphExplorer";
import Compliance from "./pages/app/Compliance";
import Connectors from "./pages/app/Connectors";
import Profile from "./pages/app/Profile";
import Interview from "./pages/app/Interview";

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
        <Route path="documents" element={<Documents />} />
        <Route path="profile" element={<Profile />} />

        {/* engineer+ */}
        <Route path="moc" element={
          <RoleRoute minRole="engineer"><Moc /></RoleRoute>
        } />
        <Route path="graph" element={
          <RoleRoute minRole="engineer"><GraphExplorer /></RoleRoute>
        } />
        <Route path="compliance" element={
          <RoleRoute minRole="engineer"><Compliance /></RoleRoute>
        } />
        <Route path="interview" element={
          <RoleRoute minRole="engineer"><Interview /></RoleRoute>
        } />

        {/* admin only */}
        <Route path="connectors" element={
          <RoleRoute minRole="admin"><Connectors /></RoleRoute>
        } />
      </Route>
    </Routes>
  );
}
