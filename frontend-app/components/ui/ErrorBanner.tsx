"use client";

import type { ApiError } from "@/types/auth";

export function ErrorBanner({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return (
    <div
      role="alert"
      className="
        p-3 rounded-lg text-sm
        bg-red-50 border border-red-200
        dark:bg-red-950/30 dark:border-red-900
      "
    >
      <p className="text-red-700 dark:text-red-400">
        {error.message}
      </p>
    </div>
  );
}
