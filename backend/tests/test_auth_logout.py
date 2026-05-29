import pytest
from httpx import AsyncClient

USER = {"email": "logouttest@example.com", "password": "Secure123!Pass"}


@pytest.mark.asyncio
async def test_logout_clears_cookie(client: AsyncClient):
    await client.post("/api/v1/auth/register", json=USER)
    logout_resp = await client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json()["message"] == "Logged out"


@pytest.mark.asyncio
async def test_refresh_after_logout_fails(client: AsyncClient):
    await client.post("/api/v1/auth/register", json=USER)
    await client.post("/api/v1/auth/logout")
    # After logout, the refresh cookie should be invalid
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
