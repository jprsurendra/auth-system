/**
 * hooks/useTokenRefresh.ts
 * ─────────────────────────
 * Silently refreshes the access token 2 minutes
 * before it expires — keeps the session alive without
 * requiring the user to re-login.
 *
 * How it works:
 *   1. Receives access_token_expires_at from AuthProvider.
 *   2. Schedules a setTimeout for (expiry - now - 2min).
 *   3. On trigger: calls POST /auth/refresh.
 *   4. On success: reschedules with the new expiry.
 *   5. On failure: clears cookies via logout and
 *      redirects to /login?reason=session_expired.
 *
 * The raw token is never touched — only the expiry
 * timestamp (from the response body) is used here.
 */

"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";

// Refresh 2 minutes before expiry
const BUFFER_MS = 2 * 60 * 1000;


export function useTokenRefresh(
  accessTokenExpiresAt: string | undefined,
) {
  const router  = useRouter();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );

  useEffect(() => {
    if (!accessTokenExpiresAt) return;

    // Clear any existing timer
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    const expiresAt   = new Date(accessTokenExpiresAt).getTime();
    const now         = Date.now();
    const msUntilRefresh = expiresAt - now - BUFFER_MS;

    if (msUntilRefresh <= 0) {
      // Already near expiry — refresh immediately
      void doRefresh();
      return;
    }

    timerRef.current = setTimeout(
      () => void doRefresh(),
      msUntilRefresh,
    );

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [accessTokenExpiresAt]);


  async function doRefresh() {
    try {
      const data = await authApi.refresh();

      // Reschedule with new expiry
      const nextMs =
        new Date(data.access_token_expires_at).getTime() -
        Date.now() -
        BUFFER_MS;

      if (nextMs > 0) {
        timerRef.current = setTimeout(
          () => void doRefresh(),
          nextMs,
        );
      }
    } catch {
      // Refresh failed — session is over
      try {
        await authApi.logout();
      } catch {
        // Ignore logout errors
      }
      router.push("/login?reason=session_expired");
    }
  }
}
