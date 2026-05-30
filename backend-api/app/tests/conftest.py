from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.security import hash_password
from app.db.redis import get_redis
from app.db.session import get_db
from app.main import create_app
from app.models.user import Base, User

# ── Use in-memory SQLite for tests ─────────────────────────────────────────────
# aiosqlite is SQLite's async driver.
# Add it to requirements.txt for test use:  aiosqlite==0.20.0
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# ── Event loop ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Database fixtures ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create all tables once per test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields a test database session.
    Wraps each test in a transaction that is rolled back afterwards —
    tests never pollute each other's data.
    """
    async with test_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


# ── Redis mock ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    """
    In-memory dict-backed Redis mock.
    Implements only the methods used by our services.
    """
    store: dict[str, Any] = {}
    ttls: dict[str, int] = {}

    redis = MagicMock()

    async def hset(key, mapping=None, **kwargs):
        store[key] = mapping or kwargs

    async def hgetall(key):
        return store.get(key, {})

    async def hincrby(key, field, amount):
        if key in store:
            store[key][field] = str(
                int(store[key].get(field, 0)) + amount
            )

    async def delete(*keys):
        for k in keys:
            store.pop(k, None)

    async def expire(key, seconds):
        ttls[key] = seconds

    async def ping():
        return True

    async def zremrangebyscore(key, min_s, max_s):
        pass

    async def zcard(key):
        return 0

    async def zadd(key, mapping):
        pass

    # Pipeline mock
    pipeline_mock = AsyncMock()
    pipeline_mock.__aenter__ = AsyncMock(
        return_value=pipeline_mock
    )
    pipeline_mock.__aexit__ = AsyncMock(return_value=False)
    pipeline_mock.zremrangebyscore = AsyncMock()
    pipeline_mock.zcard = AsyncMock()
    pipeline_mock.zadd = AsyncMock()
    pipeline_mock.expire = AsyncMock()
    pipeline_mock.execute = AsyncMock(
        return_value=[None, 0, None, None]
    )
    pipeline_mock.hset = AsyncMock()
    pipeline_mock.hincrby = AsyncMock()

    redis.hset       = hset
    redis.hgetall    = hgetall
    redis.hincrby    = hincrby
    redis.delete     = delete
    redis.expire     = expire
    redis.ping       = ping
    redis.pipeline   = MagicMock(return_value=pipeline_mock)
    redis.aclose     = AsyncMock()

    return redis


# ── App + HTTP client ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def app(db_session, mock_redis) -> FastAPI:
    """
    FastAPI app with all dependencies overridden for testing.
    No real DB connections or Redis calls are made.
    """
    fastapi_app = create_app()

    async def override_db():
        yield db_session

    async def override_redis():
        yield mock_redis

    fastapi_app.dependency_overrides[get_db]    = override_db
    fastapi_app.dependency_overrides[get_redis] = override_redis

    return fastapi_app


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client — no network calls."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ── User factories ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def unverified_user(db_session: AsyncSession) -> User:
    """A registered but unverified user."""
    user = User(
        email="unverified@example.com",
        phone="+919876543210",
        username="unverified_user",
        full_name="Unverified User",
        hashed_password=hash_password("StrongPass@123"),
        email_verified=False,
        phone_verified=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def verified_user(db_session: AsyncSession) -> User:
    """A fully verified, active user — ready to log in."""
    user = User(
        email="verified@example.com",
        phone="+919876543211",
        username="verified_user",
        full_name="Verified User",
        hashed_password=hash_password("StrongPass@123"),
        email_verified=True,
        phone_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def inactive_user(db_session: AsyncSession) -> User:
    """A verified but deactivated user."""
    user = User(
        email="inactive@example.com",
        phone="+919876543212",
        username="inactive_user",
        full_name="Inactive User",
        hashed_password=hash_password("StrongPass@123"),
        email_verified=True,
        phone_verified=True,
        is_active=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user
