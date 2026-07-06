// AuthContext.jsx — authentication via Supabase Auth.
//
// When Supabase is not configured (no env vars), the app runs in a permissive
// "demo" mode with a stub user so the dashboard is still usable locally.
import { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react';
import { supabase, isSupabaseConfigured } from '../api/client';

const AuthContext = createContext(null);

const DEMO_USER = { id: 'demo', email: 'demo@mudir.local', user_metadata: { name: 'Demo Admin' } };

export function AuthProvider({ children }) {
  const [user, setUser] = useState(isSupabaseConfigured ? null : DEMO_USER);
  const [loading, setLoading] = useState(isSupabaseConfigured);

  useEffect(() => {
    if (!isSupabaseConfigured) return undefined;
    let active = true;

    supabase.auth.getSession().then(({ data }) => {
      if (active) {
        setUser(data.session?.user ?? null);
        setLoading(false);
      }
    });

    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });

    return () => {
      active = false;
      sub?.subscription?.unsubscribe();
    };
  }, []);

  const signIn = useCallback(async ({ email, password }) => {
    if (!isSupabaseConfigured) {
      setUser(DEMO_USER);
      return DEMO_USER;
    }
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    return data.user;
  }, []);

  const signInWithGoogle = useCallback(async () => {
    if (!isSupabaseConfigured) {
      setUser(DEMO_USER);
      return;
    }
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin },
    });
    if (error) throw error;
  }, []);

  const signOut = useCallback(async () => {
    if (isSupabaseConfigured) await supabase.auth.signOut();
    setUser(isSupabaseConfigured ? null : DEMO_USER);
  }, []);

  const value = useMemo(
    () => ({ user, loading, isAuthenticated: Boolean(user), signIn, signInWithGoogle, signOut }),
    [user, loading, signIn, signInWithGoogle, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuthContext() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuthContext must be used within AuthProvider');
  return ctx;
}

export default AuthContext;
