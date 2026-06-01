"""
app/db/queries/user_queries.py

Hybrid ORM + raw SQL pattern for this project.

Rule:
  Standard CRUD operations  → ORM in endpoint files
  Complex multi-table queries → raw SQL here via text()

All queries here:
  - Use parameterised values — SQL injection impossible
  - Are separated from endpoint logic
  - Can be optimised without touching business logic
  - Serve as the foundation for future module queries
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_user_login_summary(
    db: AsyncSession,
    user_id: str,
    days: int = 30,
) -> list[dict]:
    """
    Daily login count and unique IP count
    for the given user over the past N days.

    Used for: security dashboard, anomaly detection.
    Raw SQL because GROUP BY + date_trunc is cleaner
    and faster than ORM equivalent.
    """
    result = await db.execute(
        text(
            """
            SELECT
                date_trunc('day', created_at)  AS day,
                COUNT(*)                        AS event_count,
                COUNT(DISTINCT ip_address)      AS unique_ips
            FROM audit_logs
            WHERE user_id   = :user_id
            AND   event      = 'login_success'
            AND   created_at > NOW() - INTERVAL '1 day'
                              * :days
            GROUP BY 1
            ORDER BY 1 DESC
            """
        ),
        {"user_id": user_id, "days": days},
    )
    return [dict(row._mapping) for row in result]


async def get_active_sessions_summary(
    db: AsyncSession,
    user_id: str,
) -> list[dict]:
    """
    All active sessions for a user with context.
    Used for: active sessions management page
    where users can revoke individual sessions.
    """
    result = await db.execute(
        text(
            """
            SELECT
                id,
                ip_address,
                user_agent,
                created_at,
                last_used_at,
                expires_at
            FROM user_sessions
            WHERE user_id  = :user_id
            AND   is_valid  = true
            AND   expires_at > NOW()
            ORDER BY last_used_at DESC NULLS LAST
            """
        ),
        {"user_id": user_id},
    )
    return [dict(row._mapping) for row in result]


async def get_failed_login_count(
    db: AsyncSession,
    ip_address: str,
    since: datetime,
) -> int:
    """
    Count failed login attempts from an IP since
    a given timestamp.

    Used for: enhanced security alerts when an IP
    has many failures across multiple accounts.
    Complements the Redis rate limiter.
    """
    result = await db.execute(
        text(
            """
            SELECT COUNT(*) AS attempt_count
            FROM audit_logs
            WHERE ip_address = :ip
            AND   event IN (
                'login_failed_password',
                'otp_mismatch'
            )
            AND   created_at > :since
            """
        ),
        {"ip": ip_address, "since": since},
    )
    row = result.fetchone()
    return int(row.attempt_count) if row else 0


async def get_recent_security_events(
    db: AsyncSession,
    user_id: str,
    limit: int = 20,
) -> list[dict]:
    """
    Recent security-relevant audit events for a user.
    Used for: security activity feed on account page.
    """
    result = await db.execute(
        text(
            """
            SELECT
                event,
                ip_address,
                created_at,
                detail
            FROM audit_logs
            WHERE user_id = :user_id
            AND   event IN (
                'login_success',
                'login_failed_password',
                'otp_verified',
                'otp_mismatch',
                'password_reset_completed',
                'logout',
                'refresh_token_reuse_detected'
            )
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"user_id": user_id, "limit": limit},
    )
    return [dict(row._mapping) for row in result]
