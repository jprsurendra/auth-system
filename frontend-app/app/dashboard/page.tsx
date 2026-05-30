/**
 * app/dashboard/page.tsx
 * ───────────────────────
 * Server-Side Rendered protected page.
 *
 * SSR flow:
 *   1. Next.js server reads the access_token cookie
 *      from the incoming request headers.
 *   2. Calls FastAPI /auth/me with the cookie forwarded.
 *   3. If 401 → redirect to /login (server-side, no flash).
 *   4. If 200 → render the page with full user data.
 *
 * This means the dashboard HTML is always pre-rendered
 * with real data — perfect for SEO and fast initial load.
 */

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { AuthUser } from "@/types/auth";
import { DashboardClient } from "./DashboardClient";

const INTERNAL_API =
  process.env.INTERNAL_API_URL ??
  "http://localhost:8000/api/v1";

async function getUser(): Promise<AuthUser | null> {
  const cookieStore = cookies();
  const token       = cookieStore.get("access_token")?.value;

  if (!token) return null;

  try {
    const res = await fetch(`${INTERNAL_API}/auth/me`, {
      // Forward the cookie to the backend
      headers: { Cookie: `access_token=${token}` },
      // Do not cache — always fetch fresh user data
      cache: "no-store",
    });

    if (!res.ok) return null;
    return res.json() as Promise<AuthUser>;
  } catch {
    return null;
  }
}

export default async function DashboardPage() {
  const user = await getUser();

  // Server-side redirect — no flash of unauthenticated content
  if (!user) {
    redirect("/login?reason=session_expired");
  }

  return <DashboardClient user={user} />;
}
