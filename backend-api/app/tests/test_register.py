from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"

VALID_PAYLOAD = {
    "email":     "newuser@example.com",
    "phone":     "+919876543299",
    "username":  "newuser99",
    "password":  "StrongPass@123",
    "full_name": "New User",
}


@pytest.mark.asyncio
@patch(
    "app.api.v1.endpoints.auth.send_email_verification",
    new_callable=AsyncMock,
)
@patch(
    "app.api.v1.endpoints.auth.send_sms_otp",
    new_callable=AsyncMock,
)
async def test_register_success(
    mock_sms, mock_email, client: AsyncClient
):
    res = await client.post(REGISTER_URL, json=VALID_PAYLOAD)
    assert res.status_code == 201
    data = res.json()
    assert "user_id" in data
    assert data["email_verified"] is False
    assert data["phone_verified"] is False
    mock_email.assert_called_once()
    mock_sms.assert_called_once()


@pytest.mark.asyncio
async def test_register_duplicate_email(
    client: AsyncClient, verified_user
):
    payload = {**VALID_PAYLOAD, "email": verified_user.email}
    res = await client.post(REGISTER_URL, json=payload)
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "DUPLICATE_FIELD"
    assert res.json()["detail"]["field"] == "email"


@pytest.mark.asyncio
async def test_register_duplicate_phone(
    client: AsyncClient, verified_user
):
    payload = {**VALID_PAYLOAD, "phone": verified_user.phone}
    res = await client.post(REGISTER_URL, json=payload)
    assert res.status_code == 409
    assert res.json()["detail"]["field"] == "phone"


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    payload = {**VALID_PAYLOAD, "password": "weak"}
    res = await client.post(REGISTER_URL, json=payload)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_phone(client: AsyncClient):
    payload = {**VALID_PAYLOAD, "phone": "not-a-phone"}
    res = await client.post(REGISTER_URL, json=payload)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    payload = {**VALID_PAYLOAD, "email": "not-an-email"}
    res = await client.post(REGISTER_URL, json=payload)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_register_username_special_chars(
    client: AsyncClient
):
    payload = {**VALID_PAYLOAD, "username": "bad user!"}
    res = await client.post(REGISTER_URL, json=payload)
    assert res.status_code == 422
    