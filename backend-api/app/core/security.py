from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt with cost factor 12 — ~250ms per hash (good brute-force resistance)
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12
)


# ── Password ───────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison built into passlib — safe against timing attacks."""
    return pwd_context.verify(plain, hashed)


# ── JWT ────────────────────────────────────────────────────────────────────────

def _make_token(
    subject: str,
    token_type: str,
    expires_delta: timedelta,
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": expire,
        # Unique token ID — useful for future deny-listing
        "jti": secrets.token_urlsafe(16),
    }
    token = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return token, expire


def create_access_token(user_id: str) -> tuple[str, datetime]:
    return _make_token(
        subject=user_id,
        token_type="access",
        expires_delta=timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        ),
    )


def create_refresh_token(user_id: str) -> tuple[str, datetime]:
    """
    Returns (raw_token, expires_at).
    NEVER store raw_token — only store hash_token(raw_token) in the DB.
    """
    return _make_token(
        subject=user_id,
        token_type="refresh",
        expires_delta=timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Raises jose.JWTError on any failure.
    Caller must catch and return HTTP 401.
    """
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM]
    )
    if payload.get("type") != "access":
        raise JWTError("Wrong token type")
    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM]
    )
    if payload.get("type") != "refresh":
        raise JWTError("Wrong token type")
    return payload


# ── Refresh token hashing ──────────────────────────────────────────────────────

def hash_token(raw_token: str) -> str:
    """SHA-256 hex digest — safe to store in DB."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


# ── OTP ────────────────────────────────────────────────────────────────────────

def generate_otp() -> str:
    """Cryptographically secure random numeric OTP."""
    upper_bound = 10 ** settings.OTP_LENGTH
    return str(secrets.randbelow(upper_bound)).zfill(settings.OTP_LENGTH)


def sign_otp(otp: str, identifier: str) -> str:
    """
    HMAC-SHA256 — binds the OTP to the specific identifier (email or phone).
    Prevents an attacker who reads Redis from reusing an OTP
    on a different account.
    """
    msg = f"{identifier}:{otp}".encode()
    return hmac.new(
        settings.OTP_HMAC_KEY.encode(),
        msg,
        digestmod=hashlib.sha256
    ).hexdigest()


def verify_otp_signature(
    otp: str,
    identifier: str,
    signature: str
) -> bool:
    """Constant-time comparison — prevents timing attacks."""
    expected = sign_otp(otp, identifier)
    return hmac.compare_digest(expected, signature)


# ── Cookie helpers ─────────────────────────────────────────────────────────────

COOKIE_ACCESS = "access_token"
COOKIE_REFRESH = "refresh_token"


def set_auth_cookies(
    response: Any,
    access_token: str,
    refresh_token: str,
) -> None:
    """
    Write both tokens as HttpOnly + Secure + SameSite=Strict cookies.
    JavaScript can NEVER read these — immune to XSS token theft.
    """
    common = dict(
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )
    response.set_cookie(
        key=COOKIE_ACCESS,
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **common,
    )
    response.set_cookie(
        key=COOKIE_REFRESH,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        # Scoped path — browser only sends this cookie to /refresh endpoint
        path="/api/v1/auth/refresh",
        **{k: v for k, v in common.items() if k != "path"},
    )


def clear_auth_cookies(response: Any) -> None:
    response.delete_cookie(COOKIE_ACCESS, path="/")
    response.delete_cookie(
        COOKIE_REFRESH,
        path="/api/v1/auth/refresh"
    )
