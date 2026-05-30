/**
 * lib/api.ts
 * ───────────
 * Typed API client for all backend endpoints.
 *
 * Security notes:
 *   - Every call uses credentials: "include" so the browser
 *     automatically sends and receives HttpOnly cookies.
 *   - Tokens are NEVER read, stored, or handled here —
 *     they live exclusively in HttpOnly cookies.
 *   - All errors are normalised into ApiError shape.
 */

import type {
  ApiError,
  AuthUser,
  OtpRequestResponse,
  RefreshResponse,
  RegisterResponse,
  VerificationResponse,
} from "@/types/auth";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000/api/v1";


// ── Core fetch wrapper ─────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    // CRITICAL: must be "include" for HttpOnly
    // cookie flow to work cross-origin
    credentials: "include",
    ...options,
  });

  // Try to parse body regardless of status
  let data: any;
  try {
    data = await res.json();
  } catch {
    data = {};
  }

  if (!res.ok) {
    // Normalise FastAPI error shapes into ApiError
    const err: ApiError =
      data?.error ??
      data?.detail ??
      {
        code:    "UNKNOWN_ERROR",
        message: "An unexpected error occurred.",
      };
    throw err;
  }

  return data as T;
}


// ── Auth endpoints ─────────────────────────────────────────────────────────────

export const authApi = {

  // Registration
  register: (payload: {
    email:     string;
    phone:     string;
    username:  string;
    password:  string;
    full_name: string;
  }) =>
    apiFetch<RegisterResponse>("/auth/register", {
      method: "POST",
      body:   JSON.stringify(payload),
    }),

  // Email verification
  verifyEmail: (token: string) =>
    apiFetch<VerificationResponse>("/auth/verify/email", {
      method: "POST",
      body:   JSON.stringify({ token }),
    }),

  // Phone verification
  verifyPhone: (phone: string, otp: string) =>
    apiFetch<VerificationResponse>("/auth/verify/phone", {
      method: "POST",
      body:   JSON.stringify({ phone, otp }),
    }),

  // Password login
  loginPassword: (
    username_or_email: string,
    password: string,
  ) =>
    apiFetch<AuthUser>("/auth/login/password", {
      method: "POST",
      body:   JSON.stringify({ username_or_email, password }),
    }),

  // Email OTP — request
  requestEmailOtp: (email: string) =>
    apiFetch<OtpRequestResponse>(
      "/auth/login/otp/email/request",
      {
        method: "POST",
        body:   JSON.stringify({ email }),
      },
    ),

  // Email OTP — verify
  verifyEmailOtp: (identifier: string, otp: string) =>
    apiFetch<AuthUser>("/auth/login/otp/email/verify", {
      method: "POST",
      body:   JSON.stringify({ identifier, otp }),
    }),

  // SMS OTP — request
  requestSmsOtp: (phone: string) =>
    apiFetch<OtpRequestResponse>(
      "/auth/login/otp/sms/request",
      {
        method: "POST",
        body:   JSON.stringify({ phone }),
      },
    ),

  // SMS OTP — verify
  verifySmsOtp: (identifier: string, otp: string) =>
    apiFetch<AuthUser>("/auth/login/otp/sms/verify", {
      method: "POST",
      body:   JSON.stringify({ identifier, otp }),
    }),

  // Google OAuth — get redirect URL
  getGoogleAuthUrl: async (): Promise<string> => {
    const data = await apiFetch<{ auth_url: string }>(
      "/auth/login/google",
    );
    return data.auth_url;
  },

  // Refresh tokens (silent)
  refresh: () =>
    apiFetch<RefreshResponse>("/auth/refresh", {
      method: "POST",
    }),

  // Logout
  logout: () =>
    apiFetch<{ message: string }>("/auth/logout", {
      method: "POST",
    }),

  // Get current user
  me: () => apiFetch<AuthUser>("/auth/me"),
};
