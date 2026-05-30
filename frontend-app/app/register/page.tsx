"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authApi } from "@/lib/api";
import { InputField }   from "@/components/ui/InputField";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ErrorBanner }  from "@/components/ui/ErrorBanner";
import type { ApiError } from "@/types/auth";

export default function RegisterPage() {
  const router = useRouter();

  const [form, setForm] = useState({
    full_name: "",
    email:     "",
    phone:     "",
    username:  "",
    password:  "",
    confirm:   "",
  });

  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<ApiError | null>(null);
  const [success, setSuccess] = useState(false);

  function update(field: keyof typeof form) {
    return (v: string) =>
      setForm((prev) => ({ ...prev, [field]: v }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (form.password !== form.confirm) {
      setError({
        code:    "PASSWORD_MISMATCH",
        message: "Passwords do not match.",
      });
      return;
    }

    setLoading(true);
    try {
      await authApi.register({
        full_name: form.full_name,
        email:     form.email,
        phone:     form.phone,
        username:  form.username,
        password:  form.password,
      });
      setSuccess(true);
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setLoading(false);
    }
  }

  // ── Success state ────────────────────────────────────────────
  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center
                      bg-gray-50 dark:bg-gray-950 px-4">
        <div className="w-full max-w-md text-center space-y-4">
          <div className="inline-flex items-center justify-center
                          w-16 h-16 rounded-full bg-green-100
                          dark:bg-green-900/30">
            <svg className="w-8 h-8 text-green-600"
                 fill="none" stroke="currentColor"
                 viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round"
                    strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h1 className="text-2xl font-semibold
                         text-gray-900 dark:text-white">
            Account created!
          </h1>
          <p className="text-gray-500 dark:text-gray-400">
            We have sent a verification email and SMS to your
            registered email and phone number.
            Please verify both before logging in.
          </p>
          <div className="flex flex-col gap-3 pt-2">
            <Link
              href="/verify/email"
              className="w-full py-2.5 px-4 rounded-lg
                         bg-indigo-600 hover:bg-indigo-700
                         text-white text-sm font-medium
                         text-center transition-colors"
            >
              Verify email
            </Link>
            <Link
              href="/verify/phone"
              className="w-full py-2.5 px-4 rounded-lg border
                         border-gray-300 dark:border-gray-700
                         text-gray-700 dark:text-gray-300
                         text-sm font-medium text-center
                         hover:bg-gray-50 dark:hover:bg-gray-800
                         transition-colors"
            >
              Verify phone number
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // ── Registration form ────────────────────────────────────────
  return (
    <div className="min-h-screen flex items-center justify-center
                    bg-gray-50 dark:bg-gray-950 px-4 py-12">
      <div className="w-full max-w-md">

        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center
                          w-12 h-12 rounded-xl bg-indigo-600 mb-4">
            <svg className="w-6 h-6 text-white"
                 fill="none" stroke="currentColor"
                 viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round"
                    strokeWidth={2}
                    d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12
                       14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </div>
          <h1 className="text-2xl font-semibold
                         text-gray-900 dark:text-white">
            Create an account
          </h1>
          <p className="mt-1 text-sm text-gray-500
                        dark:text-gray-400">
            Already have an account?{" "}
            <Link href="/login"
                  className="text-indigo-600 hover:text-indigo-500
                             font-medium">
              Sign in
            </Link>
          </p>
        </div>

        {/* Form card */}
        <div className="bg-white dark:bg-gray-900 rounded-2xl
                        shadow-sm border border-gray-200
                        dark:border-gray-800 p-6 space-y-4">

          <ErrorBanner error={error} />

          <form onSubmit={handleSubmit}
                className="space-y-4" noValidate>

            <InputField
              label="Full name"
              id="full_name"
              value={form.full_name}
              onChange={update("full_name")}
              placeholder="Rahul Sharma"
              autoComplete="name"
              disabled={loading}
            />

            <InputField
              label="Email address"
              id="email"
              type="email"
              value={form.email}
              onChange={update("email")}
              placeholder="rahul@example.com"
              autoComplete="email"
              disabled={loading}
            />

            <InputField
              label="Mobile number"
              id="phone"
              type="tel"
              value={form.phone}
              onChange={update("phone")}
              placeholder="+919876543210"
              autoComplete="tel"
              hint="Include country code, e.g. +91 for India"
              disabled={loading}
            />

            <InputField
              label="Username"
              id="username"
              value={form.username}
              onChange={update("username")}
              placeholder="rahul_sharma"
              autoComplete="username"
              hint="Letters, numbers, dots, dashes, underscores only"
              disabled={loading}
            />

            <InputField
              label="Password"
              id="password"
              type="password"
              value={form.password}
              onChange={update("password")}
              placeholder="Min 10 chars, upper, lower, number, symbol"
              autoComplete="new-password"
              disabled={loading}
            />

            <InputField
              label="Confirm password"
              id="confirm"
              type="password"
              value={form.confirm}
              onChange={update("confirm")}
              placeholder="Repeat your password"
              autoComplete="new-password"
              disabled={loading}
            />

            <SubmitButton loading={loading}>
              Create account
            </SubmitButton>

          </form>
        </div>

        <p className="mt-6 text-center text-xs text-gray-400">
          By registering you agree to our Terms of Service
          and Privacy Policy.
        </p>
      </div>
    </div>
  );
}
