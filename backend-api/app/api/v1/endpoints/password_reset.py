"""
app/api/v1/endpoints/password_reset.py
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiter import register_rate_limit
from app.core.security import hash_password, hash_token
from app.db.redis import get_redis
from app.db.session import get_db
from app.models.user import AuditLog, User, UserSession
from app.schemas.auth import (
    PasswordResetConfirmSchema,
    PasswordResetRequestSchema,
)
from app.services.notification_service import send_password_reset_email

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Password Reset"])

_RESET_PREFIX      = "pwd_reset:"
_RESET_TTL_SECONDS = 60 * 30  # 30 minutes


def _reset_key(token_hash: str) -> str:
    return f"{_RESET_PREFIX}{token_hash}"


async def _audit(
    db: AsyncSession,
    event: str,
    user_id: str | None,
    request: Request,
) -> None:
    db.add(AuditLog(
        user_id=user_id,
        event=event,
        ip_address=(
            request.client.host if request.client else "unknown"
        ),
        user_agent=request.headers.get("user-agent", "")[:512],
    ))


# ── Step 1 — Request reset ─────────────────────────────────────

@router.post(
    "/password-reset/request",
    status_code=status.HTTP_200_OK,
    summary="Request a password reset email",
)
async def request_password_reset(
    payload: PasswordResetRequestSchema,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
    _rate: None = Depends(register_rate_limit),
):
    """
    Always returns 200 even for unknown emails.
    Prevents attackers from discovering registered emails.
    """
    result = await db.execute(
        select(User).where(User.email == payload.email)
    )
    user = result.scalar_one_or_none()

    if user and user.is_active:
        raw_token  = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_token)

        # Store hash only — raw token never persisted
        await redis.setex(
            _reset_key(token_hash),
            _RESET_TTL_SECONDS,
            user.id,
        )

        await send_password_reset_email(
            email=user.email,
            name=user.full_name,
            token=raw_token,
        )

        await _audit(
            db, "password_reset_requested",
            user.id, request,
        )
        logger.info("password_reset_requested", user_id=user.id)

    # Same response regardless — never reveal if email exists
    return {
        "message": (
            "If this email is registered, a reset link "
            "has been sent. It expires in 30 minutes."
        )
    }


# ── Step 2 — Confirm reset ─────────────────────────────────────

@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_200_OK,
    summary="Reset password using token from email",
)
async def confirm_password_reset(
    payload: PasswordResetConfirmSchema,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis=Depends(get_redis),
):
    token_hash = hash_token(payload.token)
    redis_key  = _reset_key(token_hash)

    user_id = await redis.get(redis_key)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code":    "INVALID_TOKEN",
                "message": (
                    "This reset link is invalid or expired. "
                    "Please request a new one."
                ),
            },
        )

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        await redis.delete(redis_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code":    "ACCOUNT_INACTIVE",
                "message": "This account is inactive.",
            },
        )

    # Update password
    user.hashed_password = hash_password(
        payload.new_password.get_secret_value()
    )
    user.updated_at = datetime.now(timezone.utc)

    # Invalidate ALL active sessions on ALL devices
    sessions = await db.execute(
        select(UserSession).where(
            UserSession.user_id  == user.id,
            UserSession.is_valid == True,
        )
    )
    for session in sessions.scalars().all():
        session.is_valid = False

    # Consume token — one-time use
    await redis.delete(redis_key)

    await _audit(
        db, "password_reset_completed",
        user.id, request,
    )
    logger.info("password_reset_completed", user_id=user.id)

    return {
        "message": (
            "Password reset successfully. "
            "Please log in with your new password. "
            "All other sessions have been signed out."
        )
    }
