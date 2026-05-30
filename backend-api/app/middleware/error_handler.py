"""
app/middleware/error_handler.py
────────────────────────────────
Global error handling middleware.

Intercepts every unhandled exception and:
  1. Extracts full request context (method, URL, body, headers)
  2. Extracts user identity from the JWT cookie (if present)
  3. Looks up geo-location for the client IP
  4. Builds a structured error report
  5. Emails the report to the support team (async, non-blocking)
  6. Logs to structlog (picked up by Sentry)
  7. Returns a clean 500 JSON response to the client
     (never leaks internal details)
"""
from __future__ import annotations

import json

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.security import COOKIE_ACCESS, decode_access_token
from app.services.error_notification_service import (
    build_error_report,
    send_support_alert,
)

logger = structlog.get_logger(__name__)


async def _extract_request_info(request: Request) -> dict:
    """
    Safely extract all useful context from the request.
    Body reading is attempted once — FastAPI may have
    already consumed the stream for validated routes,
    so we fall back to empty dict gracefully.
    """
    # Try to read body (may already be consumed)
    body = {}
    try:
        raw = await request.body()
        if raw:
            body = json.loads(raw)
    except Exception:
        body = {}

    return {
        "method":     request.method,
        "url":        str(request.url),
        "endpoint":   request.url.path,
        "ip":         (
            request.headers.get(
                "X-Forwarded-For", ""
            ).split(",")[0].strip()
            or (
                request.client.host
                if request.client else "unknown"
            )
        ),
        "user_agent": request.headers.get(
            "user-agent", ""
        )[:512],
        "headers":    dict(request.headers),
        "body":       body,
    }


def _extract_user_info(request: Request) -> dict | None:
    """
    Decode the JWT access token cookie (if present)
    to identify who was logged in when the error occurred.
    Returns None if unauthenticated or token is invalid.
    """
    token = request.cookies.get(COOKIE_ACCESS)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        return {
            "id":       payload.get("sub", "unknown"),
            "email":    payload.get("email", "—"),
            "username": payload.get("username", "—"),
        }
    except JWTError:
        return None


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that wraps every request in a try/except.
    On any unhandled exception:
      - Sends a rich error report to the support team
      - Returns HTTP 500 with a safe generic message
    """

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response

        except Exception as exc:
            # Build context first — do this before anything
            # that might fail (like the email send)
            request_info = await _extract_request_info(request)
            user_info    = _extract_user_info(request)

            # Log locally via structlog → Sentry
            logger.exception(
                "unhandled_exception",
                path=request_info["endpoint"],
                method=request_info["method"],
                user_id=user_info["id"] if user_info else None,
                ip=request_info["ip"],
            )

            # Build full report and send to support team
            # Fire-and-forget — do NOT await in the hot path
            # Use create_task so it runs in the background
            import asyncio
            async def _notify():
                try:
                    report = await build_error_report(
                        exc, request_info, user_info
                    )
                    await send_support_alert(report)
                except Exception as notify_exc:
                    logger.error(
                        "error_notification_failed",
                        error=str(notify_exc),
                    )

            asyncio.create_task(_notify())

            # Return safe response — never expose internals
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code":    "INTERNAL_ERROR",
                        "message": (
                            "An unexpected error occurred. "
                            "Our support team has been notified."
                        ),
                    }
                },
            )