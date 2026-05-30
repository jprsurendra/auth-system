"use client";

interface SubmitButtonProps {
  loading:  boolean;
  children: React.ReactNode;
  fullWidth?: boolean;
}

export function SubmitButton({
  loading,
  children,
  fullWidth = true,
}: SubmitButtonProps) {
  return (
    <button
      type="submit"
      disabled={loading}
      className={`
        ${fullWidth ? "w-full" : ""}
        py-2.5 px-4 rounded-lg font-medium text-sm
        bg-indigo-600 hover:bg-indigo-700
        active:bg-indigo-800 text-white
        focus:outline-none focus:ring-2
        focus:ring-indigo-500 focus:ring-offset-2
        disabled:opacity-60 disabled:cursor-not-allowed
        transition-all duration-150
      `}
    >
      {loading ? (
        <span className="flex items-center justify-center gap-2">
          <svg
            className="animate-spin h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
          >
            <circle
              className="opacity-25"
              cx="12" cy="12" r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8v8H4z"
            />
          </svg>
          Processing…
        </span>
      ) : (
        children
      )}
    </button>
  );
}

