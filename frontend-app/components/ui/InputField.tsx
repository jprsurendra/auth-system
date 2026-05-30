"use client";

interface InputFieldProps {
  label:        string;
  id:           string;
  type?:        string;
  value:        string;
  onChange:     (v: string) => void;
  placeholder?: string;
  autoComplete?: string;
  disabled?:    boolean;
  hint?:        string;
}

export function InputField({
  label,
  id,
  type = "text",
  value,
  onChange,
  placeholder,
  autoComplete,
  disabled,
  hint,
}: InputFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={id}
        className="text-sm font-medium
                   text-gray-700 dark:text-gray-300"
      >
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        disabled={disabled}
        className="
          w-full px-3.5 py-2.5 rounded-lg border text-sm
          bg-white dark:bg-gray-900
          border-gray-300 dark:border-gray-700
          text-gray-900 dark:text-gray-100
          placeholder-gray-400 dark:placeholder-gray-600
          focus:outline-none focus:ring-2
          focus:ring-indigo-500 focus:border-transparent
          disabled:opacity-50 disabled:cursor-not-allowed
          transition-colors
        "
      />
      {hint && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {hint}
        </p>
      )}
    </div>
  );
}
