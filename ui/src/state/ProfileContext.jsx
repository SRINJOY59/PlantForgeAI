import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthProvider";
import { fetchProfile, saveProfile } from "../lib/profile";

const ProfileContext = createContext(null);

// One profile for the whole app: the top bar reads it and the profile page
// writes it, and an edit has to show up in both without a reload.
export function ProfileProvider({ children }) {
  const { user, demoMode } = useAuth();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const userId = demoMode ? "demo" : user?.id;

  useEffect(() => {
    if (!userId) return;
    let live = true;
    setLoading(true);
    fetchProfile(userId)
      .then((p) => live && setProfile(p))
      .catch((e) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [userId]);

  const update = useCallback(async (patch) => {
    const saved = await saveProfile(userId, patch);
    setProfile(saved);
    return saved;
  }, [userId]);

  return (
    <ProfileContext.Provider value={{ profile, loading, error, update }}>
      {children}
    </ProfileContext.Provider>
  );
}

export const useProfile = () => useContext(ProfileContext);
