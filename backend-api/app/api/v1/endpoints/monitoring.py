"""
app/api/v1/endpoints/monitoring.py
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.core.config import settings
from app.db.redis import get_redis
from app.db.session import engine

logger = structlog.get_logger(__name__)
router = APIRouter(
    prefix="/monitoring",
    tags=["Monitoring"],
)

_APP_START_TIME = time.time()


@router.get(
    "/db",
    summary="Database connection pool metrics",
    include_in_schema=not settings.is_production,
)
async def db_metrics():
    """
    Returns current connection pool state.

    Healthy:  checked_out is low, checked_in > 0
    Warning:  overflow > 0 (pool under pressure)
    Critical: overflow at maximum (requests queuing)

    Bug fix from reviewer:
      reviewer wrote engine.pool.total() which does
      not exist on QueuePool — removed it.
      All calls wrapped in try/except for safety.
    """
    pool = engine.pool
    try:
        pool_size   = pool.size()
        checked_in  = pool.checkedin()
        checked_out = pool.checkedout()
        overflow    = pool.overflow()
        utilisation = round(
            (checked_out / max(pool_size, 1)) * 100, 1
        ) if pool_size > 0 else 0
    except Exception as exc:
        logger.warning("pool_metrics_error", error=str(exc))
        pool_size = checked_in = checked_out = -1
        overflow  = utilisation = -1

    return {
        "pool": {
            "size":            pool_size,
            "checked_in":      checked_in,
            "checked_out":     checked_out,
            "overflow":        overflow,
            "utilisation_pct": utilisation,
        },
        "config": {
            "pool_size":       settings.DB_POOL_SIZE,
            "max_overflow":    settings.DB_MAX_OVERFLOW,
            "max_connections": (
                settings.DB_POOL_SIZE
                + settings.DB_MAX_OVERFLOW
            ),
        },
    }


@router.get(
    "/redis",
    summary="Redis health and statistics",
    include_in_schema=not settings.is_production,
)
async def redis_metrics(
    redis: Redis = Depends(get_redis),
):
    try:
        info = await redis.info()
        return {
            "status": "ok",
            "redis": {
                "version":            info.get("redis_version"),
                "connected_clients":  info.get("connected_clients"),
                "used_memory_human":  info.get("used_memory_human"),
                "keyspace_hits":      info.get("keyspace_hits"),
                "keyspace_misses":    info.get("keyspace_misses"),
                "uptime_seconds":     info.get("uptime_in_seconds"),
            },
        }
    except Exception as exc:
        logger.error("redis_metrics_failed", error=str(exc))
        return {"status": "error", "error": str(exc)}


@router.get(
    "/app",
    summary="Application uptime and version",
    include_in_schema=not settings.is_production,
)
async def app_metrics():
    uptime = int(time.time() - _APP_START_TIME)
    return {
        "version":        settings.APP_VERSION,
        "environment":    settings.APP_ENV,
        "uptime_seconds": uptime,
        "uptime_human":   _fmt_uptime(uptime),
        "timestamp_utc":  datetime.now(timezone.utc).isoformat(),
    }


def _fmt_uptime(seconds: int) -> str:
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{d}d {h}h {m}m {s}s"