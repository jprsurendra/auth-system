"use client";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { authApi } from "@/lib/api";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ErrorBanner }  from "@/components/ui/ErrorBanner";
import type { ApiError } from "@/types/auth";

export default function VerifyEmailPage() {
  const searchParams = useSearchParams();

  const [otp,     setOtp]     = useState("");
  const [email,   setEmail]   = useState("");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<ApiError | null>(null);
  const [success, setSuccess] = useState(false);

  // If the user clicked the email link, the token is in ?token=
  // Auto-submit if token param is present
  useEffect(() => {
    const token = searchParams.get("token");
    if (token) {
      void autoVerify(token);
    }
  }, []);

  async function autoVerify(token: string) {
    setLoading(true);
    try {
      await authApi.verifyEmail(token);
      setSuccess(true);
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setLoading(false);
    }
  }

  async function handleManualSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !otp) return;
    setError(null);
    setLoading(true);

    // Build the same compound token the backend expects
    const raw   = `${email}:${otp}`;
    const token = btoa(raw)
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=/g, "");

    try {
      await authApi.verifyEmail(token);
      setSuccess(true);
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setLoading(false);
    }
  }

  // ── Success ──────────────────────────────────────────────────
  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center
                      bg-gray-50 dark:bg-gray-950 px-4">
        <div className="w-full max-w-sm text-center space-y-4">
          <div className="inline-flex items-center justify-center
                          w-16 h-16 rounded-full bg-green-100
                          dark:bg-green-900/30">
            <svg className="w-8 h-8 text-green-600"
                 fill="none" stroke="currentColor"
                 viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round"
                    strokeWidth={2} d="M5 13l4 4L19 7"/>
            </svg>
          </div>
          <h1 className="text-xl font-semibold
                         text-gray-900 dark:text-white">
            Email verified!
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Your email address has been verified successfully.
            Please also verify your phone number if you
            have not done so yet.
          </p>
          <div className="flex flex-col gap-3 pt-2">
            <Link href="/verify/phone"
                  className="w-full py-2.5 px-4 rounded-lg
                             bg-indigo-600 hover:bg-indigo-700
                             text-white text-sm font-medium
                             text-center transition-colors">
              Verify phone number
            </Link>
            <Link href="/login"
                  className="w-full py-2.5 px-4 rounded-lg border
                             border-gray-300 dark:border-gray-700
                             text-gray-700 dark:text-gray-300
                             text-sm font-medium text-center
                             hover:bg-gray-50 transition-colors">
              Go to login
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // ── Auto-verifying (token in URL) ────────────────────────────
  if (loading && searchParams.get("token")) {
    return (
      <div className="min-h-screen flex items-center justify-center
                      bg-gray-50 dark:bg-gray-950">
        <div className="text-center space-y-3">
          <svg className="animate-spin h-8 w-8 text-indigo-600
                          mx-auto"
               viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12"
                    r="10" stroke="currentColor" strokeWidth="4"/>
            <path className="opacity-75" fill="currentColor"
                  d="M4 12a8 8 0 018-8v8H4z"/>
          </svg>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Verifying your email…
          </p>
        </div>
      </div>
    );
  }

  // ── Manual OTP entry form ────────────────────────────────────
  return (
    <div className="min-h-screen flex items-center justify-center
                    bg-gray-50 dark:bg-gray-950 px-4">
      <div className="w-full max-w-sm">

        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center
                          w-12 h-12 rounded-xl bg-indigo-600 mb-4">
            <svg className="w-6 h-6 text-white"
                 fill="none" stroke="currentColor"
                 viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3 8l7.89 5.26a2 2 0 002.22
                       0L21 8M5 19h14a2 2 0 002-2V7a2
                       2 0 00-2-2H5a2 2 0 00-2 2v10a2
                       2 0 002 2z"/>
            </svg>
          </div>
          <h1 className="text-2xl font-semibold
                         text-gray-900 dark:text-white">
            Verify your email
          </h1>
          <p className="mt-1 text-sm text-gray-500
                        dark:text-gray-400">
            Enter the 6-digit code sent to your inbox.
          </p>
        </div>

        <div className="bg-white dark:bg-gray-900 rounded-2xl
                        shadow-sm border border-gray-200
                        dark:border-gray-800 p-6 space-y-4">

          <ErrorBanner error={error} />

          <form onSubmit={handleManualSubmit}
                className="space-y-4" noValidate>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="email"
                     className="text-sm font-medium
                                text-gray-700 dark:text-gray-300">
                Email address
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                disabled={loading}
                className="w-full px-3.5 py-2.5 rounded-lg border
                           text-sm bg-white dark:bg-gray-900
                           border-gray-300 dark:border-gray-700
                           text-gray-900 dark:text-gray-100
                           focus:outline-none focus:ring-2
                           focus:ring-indigo-500
                           disabled:opacity-50 transition-colors"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="otp"
                     className="text-sm font-medium
                                text-gray-700 dark:text-gray-300">
                Verification code
              </label>
              <input
                id="otp"
                type="text"
                inputMode="numeric"
                value={otp}
                onChange={(e) =>
                  setOtp(e.target.value.replace(/\D/g, ""))
                }
                placeholder="000000"
                maxLength={6}
                autoComplete="one-time-code"
                disabled={loading}
                className="w-full px-3.5 py-2.5 rounded-lg border
                           text-sm text-center tracking-widest
                           text-xl font-mono
                           bg-white dark:bg-gray-900
                           border-gray-300 dark:border-gray-700
                           text-gray-900 dark:text-gray-100
                           focus:outline-none focus:ring-2
                           focus:ring-indigo-500
                           disabled:opacity-50 transition-colors"
              />
            </div>

            <SubmitButton loading={loading}>
              Verify email
            </SubmitButton>

          </form>
        </div>
      </div>
    </div>
  );
}
