/**
 * types/auth.ts
 * ─────────────
 * Shared TypeScript interfaces mirroring the FastAPI
 * Pydantic response schemas exactly.
 * Keep in sync with backend schemas/auth.py
 */

export interface TokenMetadata {
  access_token_expires_at:  string;  // ISO 8601 UTC
  refresh_token_expires_at: string;
  token_type: string;
}

export interface AuthUser {
  user_id:        string;
  username:       string;
  email:          string;
  full_name:      string;
  is_active:      boolean;
  email_verified: boolean;
  phone_verified: boolean;
  token_metadata: TokenMetadata;
}

export interface ApiError {
  code:    string;
  message: string;
  field?:  string;
}

export interface ApiErrorResponse {
  error:  ApiError;
  detail?: ApiError;
}

export interface RegisterResponse {
  user_id:        string;
  message:        string;
  email_verified: boolean;
  phone_verified: boolean;
}

export interface VerificationResponse {
  verified: boolean;
  message:  string;
}

export interface RefreshResponse {
  access_token_expires_at: string;
  message: string;
}

export interface OtpRequestResponse {
  message: string;
}
