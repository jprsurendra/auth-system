"""
app/utils/ip_info.py
─────────────────────
Async IP geolocation lookup using ipapi.co free tier.
Used in error reports to show WHERE the user was
when the error occurred.

Free tier: 1,000 requests/day — enough for error reporting.
Upgrade to ipapi.co paid or MaxMind GeoIP2 as traffic grows.
Failures are silently swallowed — geo lookup is best-effort.
"""
from __future__ import annotations

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


async def get_ip_location(ip: str) -> dict:
    """
    Returns location dict or empty dict on any failure.
    Never raises — geo lookup must not affect request handling.
    """
    # Skip lookup for private/local IPs
    if ip in ("unknown", "127.0.0.1", "localhost") or \
       ip.startswith("192.168.") or \
       ip.startswith("10.") or \
       ip.startswith("172."):
        return {"city": "Local", "country": "Dev"}

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(
                f"{settings.IPAPI_URL}/{ip}/json/"
            )
            if res.status_code == 200:
                data = res.json()
                return {
                    "city":         data.get("city", "Unknown"),
                    "region":       data.get("region", ""),
                    "country":      data.get("country_name", "Unknown"),
                    "country_code": data.get("country_code", ""),
                    "isp":          data.get("org", "Unknown"),
                    "timezone":     data.get("timezone", ""),
                }
    except Exception as exc:
        logger.warning("ip_lookup_failed", ip=ip, error=str(exc))

    return {}
