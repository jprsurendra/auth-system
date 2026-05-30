from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

import phonenumbers
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.core.config import settings


# ── Shared validators ──────────────────────────────────────────────────────────

def _normalise_email(v: str) -> str:
    return v.strip().lower()


def _validate_phone(v: str) -> str:
    """Parse and return E.164 format or raise ValueError."""
    try:
        parsed = phonenumbers.parse(v, None)
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Invalid phone number")
        return phonenumbers.format_number(
            parsed,
            phonenumbers.PhoneNumberFormat.E164
        )
    except phonenumbers.NumberParseException:
        raise ValueError(
            "Phone must be in E.164 format, e.g. +919876543210"
        )


def _validate_otp(v: str) -> str:
    v = v.strip()
    pattern = r"\d{" + str(settings.OTP_LENGTH) + r"}"
    if not re.fullmatch(pattern, v):
        raise ValueError(
            f"OTP must be exactly {settings.OTP_LENGTH} digits"
        )
    return v


def _validate_password(v: SecretStr) -> SecretStr:
    pwd = v.get_secret_value()
    errors: list[str] = []
    if len(pwd) < 10:
        errors.append("at least 10 characters")
    if not re.search(r"[A-Z]", pwd):
        errors.append("one uppercase letter")
    if not re.search(r"[a-z]", pwd):
        errors.append("one lowercase letter")
    if not re.search(r"\d", pwd):
        errors.append("one digit")
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>/?\\|`~]", pwd):
        errors.append("one special character")
    if errors:
        raise ValueError(
            "Password must contain: " + ", ".join(errors)
        )
    return v


# ── Registration ───────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email:     EmailStr
    phone:     str = Field(..., examples=["+919876543210"])
    username:  str = Field(
        ..., min_length=3, max_length=30,
        pattern=r"^[a-zA-Z0-9_.\-]+$"
    )
    password:  SecretStr
    full_name: str = Field(..., min_length=1, max_length=150)

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return _normalise_email(v)

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_phone(v)

    @field_validator("password", mode="after")
    @classmethod
    def strong_password(cls, v: SecretStr) -> SecretStr:
        return _validate_password(v)


class RegisterResponse(BaseModel):
    user_id: str
    message: str = (
        "Account created. "
        "Please verify your email and phone number."
    )
    email_verified: bool = False
    phone_verified: bool = False


# ── Verification ───────────────────────────────────────────────────────────────

class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=512)


class VerifyPhoneRequest(BaseModel):
    phone: str
    otp:   str

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_phone(v)

    @field_validator("otp", mode="before")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        return _validate_otp(v)


class VerificationResponse(BaseModel):
    verified: bool
    message:  str


# ── OTP login ──────────────────────────────────────────────────────────────────

class RequestEmailOTPRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalise(cls, v: str) -> str:
        return _normalise_email(v)


class RequestSMSOTPRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    phone: str

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_phone(v)


class VerifyOTPRequest(BaseModel):
    """Used for both email-OTP and SMS-OTP login verification."""
    model_config = ConfigDict(str_strip_whitespace=True)

    identifier: str = Field(
        ...,
        description=(
            "Email address for email-OTP login; "
            "E.164 phone number for SMS-OTP login"
        ),
    )
    otp: str

    @field_validator("otp", mode="before")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        return _validate_otp(v)


# ── Password login ─────────────────────────────────────────────────────────────

class PasswordLoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username_or_email: str = Field(..., min_length=3, max_length=254)
    password: SecretStr

    @field_validator("username_or_email", mode="before")
    @classmethod
    def normalise(cls, v: str) -> str:
        # Lowercase if it looks like an email
        return v.lower() if "@" in v else v


# ── Google OAuth ───────────────────────────────────────────────────────────────

class GoogleCallbackRequest(BaseModel):
    code:  str = Field(..., min_length=10)
    state: str = Field(..., min_length=16)


# ── Token response ─────────────────────────────────────────────────────────────

class TokenMetadata(BaseModel):
    """
    Tokens are delivered ONLY via HttpOnly cookies — never in the body.
    This schema only communicates expiry times so the frontend
    can schedule silent refresh calls.
    """
    access_token_expires_at:  datetime
    refresh_token_expires_at: datetime
    token_type: str = "Bearer"


class AuthSuccessResponse(BaseModel):
    user_id:        str
    username:       str
    email:          EmailStr
    full_name:      str
    is_active:      bool
    email_verified: bool
    phone_verified: bool
    token_metadata: TokenMetadata


# ── Refresh / logout ───────────────────────────────────────────────────────────

class RefreshResponse(BaseModel):
    access_token_expires_at: datetime
    message: str = "Tokens rotated successfully."


class LogoutResponse(BaseModel):
    message: str = "Logged out successfully."


# ── Password reset ─────────────────────────────────────────────────────────────

class PasswordResetRequestSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalise(cls, v: str) -> str:
        return _normalise_email(v)


class PasswordResetConfirmSchema(BaseModel):
    token:        str = Field(..., min_length=32, max_length=512)
    new_password: SecretStr

    @field_validator("new_password", mode="after")
    @classmethod
    def strong_password(cls, v: SecretStr) -> SecretStr:
        return _validate_password(v)


# ── Error envelope ─────────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    code:    str
    message: str
    field:   str | None = None


class ErrorResponse(BaseModel):
    """Consistent error shape returned by all endpoints."""
    error: ErrorDetail
