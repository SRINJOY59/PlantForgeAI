import { createContext, useContext, useEffect, useState } from "react";
import { supabase, supabaseEnabled } from "../lib/supabase";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(supabaseEnabled);

  useEffect(() => {
    if (!supabaseEnabled) return;
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) =>
      setSession(s)
    );
    return () => sub.subscription.unsubscribe();
  }, []);

  const value = {
    session,
    user: session?.user ?? null,
    loading,
    demoMode: !supabaseEnabled,
    signOut: () => supabaseEnabled && supabase.auth.signOut(),
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
