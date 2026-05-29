import asyncio
import pytest
from httpx import AsyncClient

USER = {"email": "refreshtest@example.com", "password": "Secure123!Pass"}


@pytest.mark.asyncio
async def test_refresh_rotates_token(client: AsyncClient):
    reg = await client.post("/api/v1/auth/register", json=USER)
    assert reg.status_code == 201
    old_access = reg.json()["access_token"]
    # Sleep 1 second so iat/exp differ (JWT has second-level precision)
    await asyncio.sleep(1)
    refresh_resp = await client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    new_token = refresh_resp.json()["access_token"]
    assert new_token != old_access
    assert "refresh_token" in refresh_resp.cookies


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_401(client: AsyncClient):
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
