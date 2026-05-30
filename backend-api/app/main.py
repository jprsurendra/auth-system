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


# Add this import at the top of main.py
from app.middleware.error_handler import ErrorHandlerMiddleware


logger = structlog.get_logger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown lifecycle manager.
    Replaces the deprecated @app.on_event pattern.
    Everything before yield runs on startup.
    Everything after yield runs on shutdown.
    """
    # ── Startup ────────────────────────────────────────────────
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.APP_ENV,
            # Sample 10% of transactions in prod to control cost
            traces_sample_rate=(
                0.1 if settings.is_production else 1.0
            ),
        )
        logger.info("sentry_initialised")

    init_redis_pool()
    logger.info("redis_pool_ready")

    logger.info(
        "app_started",
        env=settings.APP_ENV,
        version=settings.APP_VERSION,
    )

    yield

    # ── Shutdown ───────────────────────────────────────────────
    await close_redis_pool()
    logger.info("redis_pool_closed")
    logger.info("app_stopped")


# ── App factory ────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        # Disable docs in production — no API surface exposure
        docs_url=(
            "/docs"
            if not settings.is_production
            else None
        ),
        redoc_url=(
            "/redoc"
            if not settings.is_production
            else None
        ),
        openapi_url=(
            "/openapi.json"
            if not settings.is_production
            else None
        ),
        lifespan=lifespan,
    )

    # ── Middleware stack ───────────────────────────────────────
    # Order matters: middleware is applied bottom-up on request,
    # top-down on response. TrustedHost runs first on every request.

    # 1. Reject requests with unrecognised Host headers
    #    Prevents host header injection attacks
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS,
    )

    # 2. CORS — strict origin allowlist
    #    allow_credentials=True is required for HttpOnly cookie flow
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
            "X-Request-ID",
        ],
        max_age=600,
    )

    # Add this inside create_app(), after the CORSMiddleware block
    # This must be the LAST middleware added so it wraps everything
    app.add_middleware(ErrorHandlerMiddleware)

    # ── Prometheus metrics ─────────────────────────────────────
    # Exposes /metrics endpoint for Prometheus scraping
    # Tracks request count, latency, status codes per endpoint
    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/health", "/readyz", "/metrics"],
    ).instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
    )

    # ── Routers ────────────────────────────────────────────────
    app.include_router(
        auth.router,
        prefix=settings.API_V1_PREFIX,
    )

    # ── Exception handlers ─────────────────────────────────────

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ):
        """
        Convert Pydantic v2 validation errors into our
        standard ErrorResponse envelope so clients always
        receive a consistent error shape.
        """
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
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ):
        """
        Catch-all for any unhandled exception.
        Logs full traceback via structlog (picked up by Sentry).
        Never exposes internal details to the client.
        """
        logger.exception(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code":    "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                }
            },
        )

    # ── Health endpoints ───────────────────────────────────────

    @app.get(
        "/health",
        tags=["Health"],
        include_in_schema=False,
    )
    async def health():
        """
        Liveness probe — returns 200 if the process is running.
        Kubernetes restarts the pod if this fails.
        """
        return {
            "status":  "ok",
            "version": settings.APP_VERSION,
            "env":     settings.APP_ENV,
        }

    @app.get(
        "/readyz",
        tags=["Health"],
        include_in_schema=False,
    )
    async def readyz():
        """
        Readiness probe — checks Redis and DB connectivity.
        Kubernetes stops sending traffic if this returns non-200.
        Returns 503 if any dependency is unreachable.
        """
        from app.db.redis import get_redis
        from app.db.session import engine

        checks: dict[str, str] = {}

        # Check Redis
        try:
            async for redis in get_redis():
                await redis.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            logger.error("readyz_redis_fail", error=str(exc))
            checks["redis"] = "fail"

        # Check PostgreSQL
        try:
            async with engine.connect():
                pass
            checks["db"] = "ok"
        except Exception as exc:
            logger.error("readyz_db_fail", error=str(exc))
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


# ── Application instance ───────────────────────────────────────────────────────
# Imported by Gunicorn/Uvicorn as the ASGI callable

app = create_app()

