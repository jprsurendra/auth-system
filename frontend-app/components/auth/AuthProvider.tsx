/**
 * components/auth/AuthProvider.tsx
 * ─────────────────────────────────
 * React context providing the current user and auth helpers
 * to all client components.
 *
 * On mount: fetches /auth/me to hydrate user state.
 * Schedules silent token refresh via useTokenRefresh.
 * Provides logout() helper that clears server session
 * and redirects to /login.
 */

"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { useTokenRefresh } from "@/hooks/useTokenRefresh";
import type { AuthUser } from "@/types/auth";


interface AuthContextValue {
  user:     AuthUser | null;
  loading:  boolean;
  logout:   () => Promise<void>;
  setUser:  (user: AuthUser | null) => void;
}

const AuthContext = createContext<AuthContextValue>({
  user:    null,
  loading: true,
  logout:  async () => {},
  setUser: () => {},
});


export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user,    setUser]    = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Schedule silent token refresh
  useTokenRefresh(user?.token_metadata?.access_token_expires_at);

  // Hydrate user on mount
  useEffect(() => {
    authApi.me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Continue even if logout API call fails
    } finally {
      setUser(null);
      router.push("/login");
    }
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, loading, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
