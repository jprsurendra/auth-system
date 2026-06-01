"""
app/middleware/request_id.py
"""
from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):

    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:

        # Accept from client or generate fresh
        request_id = request.headers.get(
            "X-Request-ID",
            str(uuid.uuid4()),
        )

        # Sanitise — prevent header injection
        request_id = request_id[:64]
        request_id = "".join(
            c for c in request_id
            if c.isalnum() or c in "-_"
        )
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store so any endpoint can read it
        request.state.request_id = request_id

        # Bind to structlog — every log line in this
        # request automatically includes request_id
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
        )

        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()

        # Return ID so frontend can log it
        response.headers["X-Request-ID"] = request_id

        return response
    