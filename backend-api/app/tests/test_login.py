from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.user import User
from app.services.otp_service import create_and_store_otp


# ── Password login ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_password_success(
    client: AsyncClient,
    verified_user: User,
):
    res = await client.post(
        "/api/v1/auth/login/password",
        json={
            "username_or_email": verified_user.email,
            "password":          "StrongPass@123",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == verified_user.email
    assert "token_metadata" in data

    # Tokens must be in cookies — NEVER in the body
    assert "access_token"  not in data
    assert "refresh_token" not in data
    assert "access_token"  in res.cookies
    assert "refresh_token" in res.cookies


@pytest.mark.asyncio
async def test_login_password_by_username(
    client: AsyncClient,
    verified_user: User,
):
    res = await client.post(
        "/api/v1/auth/login/password",
        json={
            "username_or_email": verified_user.username,
            "password":          "StrongPass@123",
        },
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_login_password_wrong_password(
    client: AsyncClient,
    verified_user: User,
):
    res = await client.post(
        "/api/v1/auth/login/password",
        json={
            "username_or_email": verified_user.email,
            "password":          "WrongPassword@1",
        },
    )
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_password_unknown_user(
    client: AsyncClient,
):
    res = await client.post(
        "/api/v1/auth/login/password",
        json={
            "username_or_email": "nobody@example.com",
            "password":          "StrongPass@123",
        },
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_login_unverified_user_blocked(
    client: AsyncClient,
    unverified_user: User,
):
    res = await client.post(
        "/api/v1/auth/login/password",
        json={
            "username_or_email": unverified_user.email,
            "password":          "StrongPass@123",
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "ACCOUNT_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_login_inactive_user_blocked(
    client: AsyncClient,
    inactive_user: User,
):
    res = await client.post(
        "/api/v1/auth/login/password",
        json={
            "username_or_email": inactive_user.email,
            "password":          "StrongPass@123",
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "ACCOUNT_INACTIVE"


# ── Email OTP login ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch(
    "app.api.v1.endpoints.auth.send_email_otp",
    new_callable=AsyncMock,
)
async def test_request_email_otp_always_202(
    mock_send, client: AsyncClient
):
    """
    Must return 202 even for unknown emails
    to prevent email enumeration.
    """
    res = await client.post(
        "/api/v1/auth/login/otp/email/request",
        json={"email": "anyone@example.com"},
    )
    assert res.status_code == 202


@pytest.mark.asyncio
@patch(
    "app.api.v1.endpoints.auth.send_email_otp",
    new_callable=AsyncMock,
)
async def test_email_otp_login_full_flow(
    mock_send,
    client: AsyncClient,
    mock_redis,
    verified_user: User,
):
    # Step 1 — request OTP
    res = await client.post(
        "/api/v1/auth/login/otp/email/request",
        json={"email": verified_user.email},
    )
    assert res.status_code == 202

    # Step 2 — get the OTP that was stored in mock Redis
    from app.services.otp_service import _otp_key
    key  = _otp_key("email_login", verified_user.email)
    data = await mock_redis.hgetall(key)
    otp  = data["otp"]

    # Step 3 — verify OTP
    res = await client.post(
        "/api/v1/auth/login/otp/email/verify",
        json={
            "identifier": verified_user.email,
            "otp":        otp,
        },
    )
    assert res.status_code == 200
    assert "access_token" in res.cookies


@pytest.mark.asyncio
async def test_email_otp_wrong_code(
    client: AsyncClient,
    mock_redis,
    verified_user: User,
):
    await create_and_store_otp(
        mock_redis, "email_login", verified_user.email
    )
    res = await client.post(
        "/api/v1/auth/login/otp/email/verify",
        json={
            "identifier": verified_user.email,
            "otp":        "000000",
        },
    )
    assert res.status_code == 401


# ── SMS OTP login ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch(
    "app.api.v1.endpoints.auth.send_sms_otp",
    new_callable=AsyncMock,
)
async def test_sms_otp_login_full_flow(
    mock_send,
    client: AsyncClient,
    mock_redis,
    verified_user: User,
):
    # Step 1 — request OTP
    res = await client.post(
        "/api/v1/auth/login/otp/sms/request",
        json={"phone": verified_user.phone},
    )
    assert res.status_code == 202

    # Step 2 — retrieve stored OTP from mock Redis
    from app.services.otp_service import _otp_key
    key  = _otp_key("sms_login", verified_user.phone)
    data = await mock_redis.hgetall(key)
    otp  = data["otp"]

    # Step 3 — verify
    res = await client.post(
        "/api/v1/auth/login/otp/sms/verify",
        json={
            "identifier": verified_user.phone,
            "otp":        otp,
        },
    )
    assert res.status_code == 200
    assert "access_token" in res.cookies
    