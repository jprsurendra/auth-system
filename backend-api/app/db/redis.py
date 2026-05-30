from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import settings

# Module-level pool — created once on startup, shared across all requests.
# hiredis C extension (declared in requirements.txt) gives 10x parse speed.
_pool: aioredis.ConnectionPool | None = None


def init_redis_pool() -> aioredis.ConnectionPool:
    global _pool
    _pool = aioredis.ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        decode_responses=True,
    )
    return _pool


async def close_redis_pool() -> None:
    global _pool
    if _pool:
        await _pool.disconnect()
        _pool = None


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency — yields a connection from the shared pool."""
    if _pool is None:
        raise RuntimeError(
            "Redis pool not initialised. "
            "Ensure init_redis_pool() is called in the lifespan handler."
        )
    client = Redis(connection_pool=_pool)
    try:
        yield client
    finally:
        await client.aclose()
