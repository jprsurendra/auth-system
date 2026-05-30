from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.user import User


async def _login(
    client: AsyncClient,
    user: User,
) -> None:
    """Helper — log in and attach cookies to the client."""
    await client.post(
        "/api/v1/auth/login/password",
        json={
            "username_or_email": user.email,
            "password":          "StrongPass@123",
        },
    )


@pytest.mark.asyncio
async def test_get_me_authenticated(
    client: AsyncClient,
    verified_user: User,
):
    await _login(client, verified_user)
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 200
    assert res.json()["email"] == verified_user.email


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_refresh_tokens(
    client: AsyncClient,
    verified_user: User,
):
    await _login(client, verified_user)

    # Capture the original access token cookie value
    original = client.cookies.get("access_token")

    res = await client.post("/api/v1/auth/refresh")
    assert res.status_code == 200
    assert "access_token_expires_at" in res.json()

    # New access token must be different from the old one
    new_token = client.cookies.get("access_token")
    assert new_token != original


@pytest.mark.asyncio
async def test_logout_clears_cookies(
    client: AsyncClient,
    verified_user: User,
):
    await _login(client, verified_user)

    res = await client.post("/api/v1/auth/logout")
    assert res.status_code == 200

    # After logout the protected endpoint must return 401
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_refresh_after_logout_fails(
    client: AsyncClient,
    verified_user: User,
):
    await _login(client, verified_user)
    await client.post("/api/v1/auth/logout")

    # Refresh token has been invalidated — must return 401
    res = await client.post("/api/v1/auth/refresh")
    assert res.status_code == 401


# ── OTP replay protection ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_otp_cannot_be_reused(
    client: AsyncClient,
    mock_redis,
    verified_user: User,
):
    from app.services.otp_service import (
        _otp_key,
        create_and_store_otp,
    )

    otp = await create_and_store_otp(
        mock_redis, "email_login", verified_user.email
    )

    # First use — succeeds
    res1 = await client.post(
        "/api/v1/auth/login/otp/email/verify",
        json={
            "identifier": verified_user.email,
            "otp":        otp,
        },
    )
    assert res1.status_code == 200

    # Second use of the same OTP — must fail
    res2 = await client.post(
        "/api/v1/auth/login/otp/email/verify",
        json={
            "identifier": verified_user.email,
            "otp":        otp,
        },
    )
    assert res2.status_code == 401
