"use client";

import { useAuth } from "@/components/auth/AuthProvider";
import type { AuthUser } from "@/types/auth";

export function DashboardClient({
  user,
}: {
  user: AuthUser;
}) {
  const { logout } = useAuth();

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">

      {/* Navbar */}
      <nav className="bg-white dark:bg-gray-900 border-b
                      border-gray-200 dark:border-gray-800">
        <div className="max-w-5xl mx-auto px-4 py-3
                        flex items-center justify-between">
          <span className="font-semibold text-gray-900
                           dark:text-white">
            AuthSystem
          </span>
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-500
                             dark:text-gray-400">
              {user.email}
            </span>
            <button
              onClick={logout}
              className="text-sm text-red-600 hover:text-red-500
                         font-medium transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </nav>

      {/* Content */}
      <main className="max-w-5xl mx-auto px-4 py-10">

        <h1 className="text-2xl font-semibold
                       text-gray-900 dark:text-white mb-6">
          Welcome, {user.full_name}
        </h1>

        {/* Verification status */}
        {(!user.email_verified || !user.phone_verified) && (
          <div className="mb-6 p-4 rounded-xl
                          bg-amber-50 border border-amber-200
                          dark:bg-amber-950/20
                          dark:border-amber-900">
            <p className="text-sm font-medium text-amber-800
                          dark:text-amber-400 mb-2">
              Action required — complete your verification
            </p>
            <div className="flex gap-3">
              {!user.email_verified && (
                <a href="/verify/email"
                   className="text-xs px-3 py-1.5 rounded-lg
                              bg-amber-600 text-white
                              hover:bg-amber-700 transition-colors">
                  Verify email
                </a>
              )}
              {!user.phone_verified && (
                <a href="/verify/phone"
                   className="text-xs px-3 py-1.5 rounded-lg
                              bg-amber-600 text-white
                              hover:bg-amber-700 transition-colors">
                  Verify phone
                </a>
              )}
            </div>
          </div>
        )}

        {/* Profile card */}
        <div className="bg-white dark:bg-gray-900 rounded-2xl
                        border border-gray-200 dark:border-gray-800
                        p-6">
          <h2 className="text-base font-semibold
                         text-gray-900 dark:text-white mb-4">
            Profile
          </h2>
          <dl className="space-y-3">
            {[
              ["User ID",  user.user_id],
              ["Username", user.username],
              ["Email",    user.email],
              ["Full name", user.full_name],
              [
                "Email verified",
                user.email_verified ? "Yes" : "No",
              ],
              [
                "Phone verified",
                user.phone_verified ? "Yes" : "No",
              ],
            ].map(([label, value]) => (
              <div
                key={label}
                className="flex gap-4 py-2 border-b
                           border-gray-100 dark:border-gray-800
                           last:border-0"
              >
                <dt className="w-36 text-sm text-gray-500
                               dark:text-gray-400 shrink-0">
                  {label}
                </dt>
                <dd className="text-sm text-gray-900
                               dark:text-gray-100 break-all">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </div>

      </main>
    </div>
  );
}
