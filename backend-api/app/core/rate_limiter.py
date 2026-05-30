from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from app.core.config import settings
from app.db.redis import get_redis

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RateLimitConfig:
    endpoint: str
    max_requests: int
    window_seconds: int


async def _check_rate_limit(
    redis: Redis,
    config: RateLimitConfig,
    ip: str,
) -> None:
    """
    Sliding-window rate limiter using Redis sorted sets.

    Why sorted sets over a simple counter?
    A fixed-window counter resets sharply at the boundary, allowing
    burst attacks that straddle two windows. The sliding window gives
    a true rolling count — O(log N) per request.

    All 4 Redis commands are pipelined into a single round-trip.
    """
    key = f"rl:{config.endpoint}:{ip}"
    now_ms = int(time.time() * 1000)
    window_start_ms = now_ms - (config.window_seconds * 1000)

    async with redis.pipeline(transaction=True) as pipe:
        # 1. Remove entries older than the window
        pipe.zremrangebyscore(key, "-inf", window_start_ms)
        # 2. Count requests in current window
        pipe.zcard(key)
        # 3. Add this request
        pipe.zadd(key, {str(now_ms): now_ms})
        # 4. Set TTL so orphan keys auto-expire
        pipe.expire(key, config.window_seconds)
        results = await pipe.execute()

    # results[1] is the count BEFORE this request was added
    current_count: int = results[1]

    if current_count >= config.max_requests:
        logger.warning(
            "rate_limit_exceeded",
            endpoint=config.endpoint,
            ip=ip,
            count=current_count,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": (
                    f"Too many requests. Max {config.max_requests} "
                    f"per {config.window_seconds} seconds."
                ),
                "retry_after_seconds": config.window_seconds,
            },
            headers={"Retry-After": str(config.window_seconds)},
        )


def _get_client_ip(request: Request) -> str:
    """
    Extract real client IP.
    Only trust X-Forwarded-For when sitting behind a known proxy.
    Spoofing XFF from a direct client is trivial — nginx/ALB
    must overwrite this header before it reaches the app.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def make_rate_limiter(config: RateLimitConfig):
    """
    Factory — returns a FastAPI dependency for the given config.

    Usage:
        @router.post("/login")
        async def login(_: None = Depends(login_rate_limit)):
            ...
    """
    async def _dependency(
        request: Request,
        redis: Annotated[Redis, Depends(get_redis)],
    ) -> None:
        ip = _get_client_ip(request)
        await _check_rate_limit(redis, config, ip)

    return _dependency


# ── Named limiters — one per sensitive endpoint ────────────────────────────────

otp_rate_limit = make_rate_limiter(RateLimitConfig(
    endpoint="otp",
    max_requests=settings.RATE_LIMIT_OTP_MAX,
    window_seconds=settings.RATE_LIMIT_OTP_WINDOW_SECONDS,
))

login_rate_limit = make_rate_limiter(RateLimitConfig(
    endpoint="login",
    max_requests=settings.RATE_LIMIT_LOGIN_MAX,
    window_seconds=settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
))

register_rate_limit = make_rate_limiter(RateLimitConfig(
    endpoint="register",
    max_requests=settings.RATE_LIMIT_REGISTER_MAX,
    window_seconds=settings.RATE_LIMIT_REGISTER_WINDOW_SECONDS,
))
