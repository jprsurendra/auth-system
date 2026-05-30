# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Builder
# Install all dependencies into an isolated virtual environment.
# gcc and libpq-dev are needed to compile asyncpg and cryptography.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install OS build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python packages
# Copy only requirements first to maximise Docker layer caching —
# this layer is only rebuilt when requirements.txt changes.
COPY requirements.txt .
RUN pip install --upgrade pip wheel \
    && pip install --no-cache-dir -r requirements.txt


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Runtime
# Lean image — no compiler, no build tools, no pip cache.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: create a dedicated non-root user
# The app process never runs as root
RUN groupadd --gid 1001 appgroup \
    && useradd \
        --uid 1001 \
        --gid appgroup \
        --no-create-home \
        --shell /bin/false \
        appuser

WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application source
COPY --chown=appuser:appgroup ./app ./app

# Environment
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Switch to non-root user
USER appuser

# Expose application port
EXPOSE 8000

# Docker-level health check
# Kubernetes uses /health and /readyz probes separately
HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=15s \
    --retries=3 \
    CMD python -c \
        "import urllib.request; \
         urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

# ─────────────────────────────────────────────────────────────────────────────
# Production entrypoint
#
# Gunicorn manages worker processes; each worker is an async
# Uvicorn instance. Worker count = 2 * CPU + 1 is the standard
# heuristic for async I/O-bound apps.
#
# Override WEB_CONCURRENCY via environment variable in Kubernetes
# rather than rebuilding the image for different instance sizes.
# ─────────────────────────────────────────────────────────────────────────────
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers",      "4", \
     "--bind",         "0.0.0.0:8000", \
     "--timeout",      "30", \
     "--graceful-timeout", "30", \
     "--keep-alive",   "5", \
     "--access-logfile",  "-", \
     "--error-logfile",   "-", \
     "--log-level",    "info"]

