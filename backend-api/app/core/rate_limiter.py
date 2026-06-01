"""
app/core/rate_limiter.py — UPDATED
Adds X-RateLimit-* headers to every response.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis

from app.core.config import settings
from app.db.redis import get_redis

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RateLimitConfig:
    endpoint: str
    max_requests: int
    window_seconds: int


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _check_rate_limit(
    redis: Redis,
    config: RateLimitConfig,
    ip: str,
    response: Response,
) -> None:
    key          = f"rl:{config.endpoint}:{ip}"
    now_ms       = int(time.time() * 1000)
    window_start = now_ms - (config.window_seconds * 1000)
    reset_ts     = int(time.time()) + config.window_seconds

    async with redis.pipeline(transaction=True) as pipe:
        pipe.zremrangebyscore(key, "-inf", window_start)
        pipe.zcard(key)
        pipe.zadd(key, {str(now_ms): now_ms})
        pipe.expire(key, config.window_seconds)
        results = await pipe.execute()

    current_count: int = results[1]
    remaining = max(0, config.max_requests - current_count - 1)

    # Set on every response so clients know their quota
    response.headers["X-RateLimit-Limit"]     = str(config.max_requests)
    response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
    response.headers["X-RateLimit-Reset"]     = str(reset_ts)
    response.headers["X-RateLimit-Window"]    = str(config.window_seconds)

    if current_count >= config.max_requests:
        logger.warning(
            "rate_limit_exceeded",
            endpoint=config.endpoint,
            ip=ip,
            count=current_count,
        )
        response.headers["X-RateLimit-Remaining"] = "0"
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code":    "RATE_LIMIT_EXCEEDED",
                "message": (
                    f"Too many requests. Max {config.max_requests} "
                    f"per {config.window_seconds} seconds."
                ),
                "retry_after_seconds": config.window_seconds,
                "reset_at": reset_ts,
            },
            headers={
                "Retry-After":          str(config.window_seconds),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset":    str(reset_ts),
            },
        )


def make_rate_limiter(config: RateLimitConfig):
    async def _dependency(
        request: Request,
        response: Response,
        redis: Annotated[Redis, Depends(get_redis)],
    ) -> None:
        ip = _get_client_ip(request)
        await _check_rate_limit(redis, config, ip, response)
    return _dependency


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