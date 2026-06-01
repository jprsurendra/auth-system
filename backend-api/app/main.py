"""
app/main.py — UPDATED
Changes from original:
  1. RequestIDMiddleware added — must be first
  2. SecurityHeadersMiddleware added
  3. expose_headers added to CORSMiddleware
  4. X-Request-ID added to allow_headers
  5. password_reset router registered
  6. monitoring router registered
  7. request_id included in 500 error responses
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.endpoints import auth
from app.core.config import settings
from app.db.redis import close_redis_pool, init_redis_pool

# NEW — new middleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

# NEW — new routers
from app.api.v1.endpoints import password_reset
from app.api.v1.endpoints import monitoring

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.APP_ENV,
            traces_sample_rate=(
                0.1 if settings.is_production else 1.0
            ),
        )
    init_redis_pool()
    logger.info(
        "app_started",
        env=settings.APP_ENV,
        version=settings.APP_VERSION,
    )
    yield
    await close_redis_pool()
    logger.info("app_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url=(
            "/docs" if not settings.is_production else None
        ),
        redoc_url=(
            "/redoc" if not settings.is_production else None
        ),
        openapi_url=(
            "/openapi.json"
            if not settings.is_production else None
        ),
        lifespan=lifespan,
    )

    # ── Middleware stack ───────────────────────────────────────
    # NEW — must be first so request_id is available
    # to all middleware and endpoints below it
    app.add_middleware(RequestIDMiddleware)

    # NEW — security headers on every response
    app.add_middleware(SecurityHeadersMiddleware)

    # Existing — unchanged
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS,
    )

    # UPDATED — expose_headers and X-Request-ID added
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            str(o) for o in settings.ALLOWED_ORIGINS
        ],
        allow_credentials=True,
        allow_methods=[
            "GET", "POST", "PUT", "DELETE", "OPTIONS"
        ],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Request-ID",       # NEW
        ],
        expose_headers=[          # NEW — browser JS can read these
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-Request-ID",
        ],
        max_age=600,
    )

    # Existing error handler — unchanged
    from app.middleware.error_handler import ErrorHandlerMiddleware
    app.add_middleware(ErrorHandlerMiddleware)

    # Existing Prometheus — unchanged
    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/health", "/readyz", "/metrics"],
    ).instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
    )

    # ── Routers ────────────────────────────────────────────────
    # Existing
    app.include_router(
        auth.router,
        prefix=settings.API_V1_PREFIX,
    )
    # NEW
    app.include_router(
        password_reset.router,
        prefix=settings.API_V1_PREFIX,
    )
    # NEW
    app.include_router(
        monitoring.router,
        prefix=settings.API_V1_PREFIX,
    )

    # ── Exception handlers ─────────────────────────────────────

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        request: Request,
        exc: RequestValidationError,
    ):
        # Unchanged from original
        errors = [
            {
                "code":    "VALIDATION_ERROR",
                "field":   ".".join(
                    str(loc) for loc in e["loc"][1:]
                ),
                "message": e["msg"],
            }
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"errors": errors},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(
        request: Request,
        exc: Exception,
    ):
        logger.exception(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            # NEW — request_id in every error log
            request_id=getattr(
                request.state, "request_id", "unknown"
            ),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code":    "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                    # NEW — user quotes this when contacting support
                    "request_id": getattr(
                        request.state, "request_id", None
                    ),
                }
            },
        )

    # ── Health endpoints — unchanged ───────────────────────────

    @app.get("/health", include_in_schema=False)
    async def health():
        return {
            "status":  "ok",
            "version": settings.APP_VERSION,
            "env":     settings.APP_ENV,
        }

    @app.get("/readyz", include_in_schema=False)
    async def readyz():
        from app.db.redis import get_redis
        from app.db.session import engine
        checks: dict[str, str] = {}
        try:
            async for redis in get_redis():
                await redis.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "fail"
        try:
            async with engine.connect():
                pass
            checks["db"] = "ok"
        except Exception:
            checks["db"] = "fail"
        all_ok = all(v == "ok" for v in checks.values())
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={
                "status": "ok" if all_ok else "degraded",
                "checks": checks,
            },
        )

    return app


app = create_app()