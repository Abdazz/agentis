import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_rate_limit_returns_429_with_headers(client: AsyncClient):
    """
    Mock the per-email rate check to raise 429 and verify the response.
    """
    from fastapi import HTTPException

    async def always_limited(email: str):
        raise HTTPException(
            status_code=429,
            headers={
                "Retry-After": "900",
            },
            detail={"code": "rate_limited", "message": "Too many failed login attempts. Try again in 15 minutes."},
        )

    # Patch the per-email rate check helper in the auth router
    with patch("app.routers.auth._redis_login_rate_check", side_effect=always_limited):
        response = await client.post("/api/v1/auth/login", json={
            "email": "test@example.com", "password": "Secure123!Pass"
        })

    assert response.status_code == 429
    assert response.headers.get("Retry-After") == "900"
    assert response.json()["error"]["code"] == "rate_limited"


@pytest.mark.asyncio
async def test_rate_limit_not_triggered_normally(client: AsyncClient):
    """Normal requests are not rate limited when under the failure threshold."""

    async def no_limit(email: str):
        pass  # Don't raise — allow the request through

    async def no_increment(email: str):
        pass

    async def no_clear(email: str):
        pass

    with patch("app.routers.auth._redis_login_rate_check", side_effect=no_limit), \
         patch("app.routers.auth._redis_login_increment", side_effect=no_increment), \
         patch("app.routers.auth._redis_login_clear", side_effect=no_clear):
        response = await client.post("/api/v1/auth/login", json={
            "email": "test@example.com", "password": "Secure123!Pass"
        })

    # 401 (wrong creds) NOT 429
    assert response.status_code == 401
