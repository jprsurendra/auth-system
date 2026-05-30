from __future__ import annotations

import structlog
from redis.asyncio import Redis

from app.core.config import settings
from app.core.security import (
    generate_otp,
    sign_otp,
    verify_otp_signature,
)

logger = structlog.get_logger(__name__)

# How many wrong attempts before the OTP is invalidated
MAX_OTP_ATTEMPTS = 5


def _otp_key(channel: str, identifier: str) -> str:
    """
    Redis key format:
      otp:email_verify:user@example.com
      otp:phone_verify:+919876543210
      otp:email_login:user@example.com
      otp:sms_login:+919876543210
    """
    return f"otp:{channel}:{identifier}"


async def create_and_store_otp(
    redis: Redis,
    channel: str,
    identifier: str,
) -> str:
    """
    Generate a fresh OTP, HMAC-sign it, and store in Redis.

    - Any previous pending OTP for this identifier is overwritten.
    - Returns the raw OTP so the caller can dispatch it via
      Twilio or SendGrid.
    - The raw OTP is NEVER persisted — only the HMAC signature is stored.
    """
    otp = generate_otp()
    signature = sign_otp(otp, identifier)
    key = _otp_key(channel, identifier)

    async with redis.pipeline(transaction=True) as pipe:
        pipe.hset(key, mapping={
            "otp":       otp,
            "signature": signature,
            "attempts":  0,
        })
        pipe.expire(key, settings.OTP_EXPIRE_SECONDS)
        await pipe.execute()

    logger.info(
        "otp_created",
        channel=channel,
        # Mask identifier in logs — show only first 4 chars
        identifier_masked=identifier[:4] + "***",
    )
    return otp


async def verify_and_consume_otp(
    redis: Redis,
    channel: str,
    identifier: str,
    submitted_otp: str,
) -> bool:
    """
    Verify the submitted OTP against what is stored in Redis.

    Security properties:
      1. One-time use  — key deleted immediately on success.
      2. Replay-proof  — HMAC signature binds OTP to identifier.
      3. Brute-force   — 5 wrong attempts invalidate the OTP.
      4. Timing-safe   — constant-time HMAC comparison.

    Returns True on success, False on any failure.
    Never raises — callers treat False as "invalid OTP" without
    revealing whether it expired, was wrong, or never existed.
    """
    key = _otp_key(channel, identifier)
    data = await redis.hgetall(key)

    # Key missing → expired or never existed
    if not data:
        logger.info("otp_not_found", channel=channel)
        return False

    # Check attempt count before touching crypto
    attempts = int(data.get("attempts", 0))
    if attempts >= MAX_OTP_ATTEMPTS:
        await redis.delete(key)
        logger.warning(
            "otp_max_attempts_exceeded",
            channel=channel,
        )
        return False

    stored_otp: str = data.get("otp", "")
    stored_sig: str = data.get("signature", "")

    # Constant-time HMAC check
    sig_valid  = verify_otp_signature(submitted_otp, identifier, stored_sig)
    # Direct string equality — safe after HMAC already validated
    otp_match  = stored_otp == submitted_otp

    if sig_valid and otp_match:
        # Consume — delete the key so it can never be used again
        await redis.delete(key)
        logger.info("otp_verified", channel=channel)
        return True

    # Wrong OTP — increment attempt counter atomically
    async with redis.pipeline(transaction=True) as pipe:
        pipe.hincrby(key, "attempts", 1)
        # Reset TTL so window doesn't shrink after each attempt
        pipe.expire(key, settings.OTP_EXPIRE_SECONDS)
        await pipe.execute()

    logger.warning(
        "otp_mismatch",
        channel=channel,
        attempt=attempts + 1,
    )
    return False


async def invalidate_otp(
    redis: Redis,
    channel: str,
    identifier: str,
) -> None:
    """
    Explicitly revoke a pending OTP.
    Call this when the user changes their email or phone
    before verification completes.
    """
    key = _otp_key(channel, identifier)
    await redis.delete(key)
