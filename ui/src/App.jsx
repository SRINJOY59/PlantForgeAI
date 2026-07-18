import { Route, Routes } from "react-router-dom";
import ProtectedRoute from "./auth/ProtectedRoute";
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
        <Route index element={<Ask />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="moc" element={<Moc />} />
        <Route path="graph" element={<GraphExplorer />} />
        <Route path="documents" element={<Documents />} />
        <Route path="compliance" element={<Compliance />} />
        <Route path="connectors" element={<Connectors />} />
        <Route path="profile" element={<Profile />} />
        <Route path="interview" element={<Interview />} />
      </Route>
    </Routes>
  );
}
