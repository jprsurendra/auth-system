"use client";

import { useState } from "react";
import Link from "next/link";
import { authApi } from "@/lib/api";
import { InputField }   from "@/components/ui/InputField";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ErrorBanner }  from "@/components/ui/ErrorBanner";
import type { ApiError } from "@/types/auth";

type Step = "enter_phone" | "enter_otp" | "success";

export default function VerifyPhonePage() {
  const [step,    setStep]    = useState<Step>("enter_phone");
  const [phone,   setPhone]   = useState("");
  const [otp,     setOtp]     = useState("");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<ApiError | null>(null);

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await authApi.verifyPhone(phone, otp);
      setStep("success");
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setLoading(false);
    }
  }

  if (step === "success") {
    return (
      <div className="min-h-screen flex items-center justify-center
                      bg-gray-50 dark:bg-gray-950 px-4">
        <div className="w-full max-w-sm text-center space-y-4">
          <div className="inline-flex items-center justify-center
                          w-16 h-16 rounded-full bg-green-100">
            <svg className="w-8 h-8 text-green-600"
                 fill="none" stroke="currentColor"
                 viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round"
                    strokeWidth={2} d="M5 13l4 4L19 7"/>
            </svg>
          </div>
          <h1 className="text-xl font-semibold
                         text-gray-900 dark:text-white">
            Phone verified!
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Your account is now fully verified.
            You can log in now.
          </p>
          <Link href="/login"
                className="block w-full py-2.5 px-4 rounded-lg
                           bg-indigo-600 hover:bg-indigo-700
                           text-white text-sm font-medium
                           text-center transition-colors">
            Go to login
          </Link>
        </div>
      </div>
    );
  }

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
                    d="M12 18h.01M8 21h8a2 2 0 002-2V5a2
                       2 0 00-2-2H8a2 2 0 00-2 2v14a2
                       2 0 002 2z"/>
            </svg>
          </div>
          <h1 className="text-2xl font-semibold
                         text-gray-900 dark:text-white">
            Verify your phone
          </h1>
          <p className="mt-1 text-sm text-gray-500
                        dark:text-gray-400">
            {step === "enter_phone"
              ? "Enter your registered mobile number."
              : `Enter the 6-digit code sent to ${phone}`}
          </p>
        </div>

        <div className="bg-white dark:bg-gray-900 rounded-2xl
                        shadow-sm border border-gray-200
                        dark:border-gray-800 p-6 space-y-4">

          <ErrorBanner error={error} />

          <form onSubmit={handleVerify}
                className="space-y-4" noValidate>

            <InputField
              label="Mobile number"
              id="phone"
              type="tel"
              value={phone}
              onChange={setPhone}
              placeholder="+919876543210"
              autoComplete="tel"
              disabled={loading || step === "enter_otp"}
              hint="E.164 format with country code"
            />

            {step === "enter_otp" && (
              <div className="flex flex-col gap-1.5">
                <label htmlFor="otp"
                       className="text-sm font-medium
                                  text-gray-700 dark:text-gray-300">
                  SMS code
                </label>
                <input
                  id="otp"
                  type="text"
                  inputMode="numeric"
                  value={otp}
                  onChange={(e) =>
                    setOtp(e.target.value.replace(/\D/g, ""))
                  }
                  maxLength={6}
                  placeholder="000000"
                  autoComplete="one-time-code"
                  disabled={loading}
                  className="w-full px-3.5 py-2.5 rounded-lg border
                             text-xl font-mono text-center
                             tracking-widest
                             bg-white dark:bg-gray-900
                             border-gray-300 dark:border-gray-700
                             text-gray-900 dark:text-gray-100
                             focus:outline-none focus:ring-2
                             focus:ring-indigo-500
                             disabled:opacity-50 transition-colors"
                />
              </div>
            )}

            {step === "enter_phone" ? (
              <button
                type="button"
                disabled={loading || !phone}
                onClick={() => {
                  setError(null);
                  setStep("enter_otp");
                }}
                className="w-full py-2.5 px-4 rounded-lg
                           font-medium text-sm text-white
                           bg-indigo-600 hover:bg-indigo-700
                           disabled:opacity-60
                           disabled:cursor-not-allowed
                           transition-colors"
              >
                Send OTP
              </button>
            ) : (
              <>
                <SubmitButton loading={loading}>
                  Verify phone
                </SubmitButton>
                <button
                  type="button"
                  className="w-full text-xs text-gray-500
                             hover:text-indigo-600 transition-colors"
                  onClick={() => {
                    setStep("enter_phone");
                    setOtp("");
                    setError(null);
                  }}
                >
                  Use a different number
                </button>
              </>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}
