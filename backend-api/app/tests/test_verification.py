from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.otp_service import create_and_store_otp


@pytest.mark.asyncio
async def test_verify_email_success(
    client: AsyncClient,
    mock_redis,
    unverified_user: User,
):
    # Create a real OTP in the mock Redis store
    otp = await create_and_store_otp(
        mock_redis, "email_verify",
        unverified_user.email,
    )
    raw = f"{unverified_user.email}:{otp}"
    token = base64.urlsafe_b64encode(
        raw.encode()
    ).decode()

    res = await client.post(
        "/api/v1/auth/verify/email",
        json={"token": token},
    )
    assert res.status_code == 200
    assert res.json()["verified"] is True


@pytest.mark.asyncio
async def test_verify_email_invalid_token(
    client: AsyncClient,
):
    res = await client.post(
        "/api/v1/auth/verify/email",
        json={"token": "invalidtoken123"},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_verify_email_wrong_otp(
    client: AsyncClient,
    mock_redis,
    unverified_user: User,
):
    # Store a real OTP but submit a wrong one
    await create_and_store_otp(
        mock_redis, "email_verify",
        unverified_user.email,
    )
    raw = f"{unverified_user.email}:000000"
    token = base64.urlsafe_b64encode(
        raw.encode()
    ).decode()

    res = await client.post(
        "/api/v1/auth/verify/email",
        json={"token": token},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_verify_phone_success(
    client: AsyncClient,
    mock_redis,
    unverified_user: User,
):
    otp = await create_and_store_otp(
        mock_redis, "phone_verify",
        unverified_user.phone,
    )
    res = await client.post(
        "/api/v1/auth/verify/phone",
        json={
            "phone": unverified_user.phone,
            "otp":   otp,
        },
    )
    assert res.status_code == 200
    assert res.json()["verified"] is True


@pytest.mark.asyncio
async def test_verify_phone_wrong_otp(
    client: AsyncClient,
    mock_redis,
    unverified_user: User,
):
    await create_and_store_otp(
        mock_redis, "phone_verify",
        unverified_user.phone,
    )
    res = await client.post(
        "/api/v1/auth/verify/phone",
        json={
            "phone": unverified_user.phone,
            "otp":   "000000",
        },
    )
    assert res.status_code == 400
    