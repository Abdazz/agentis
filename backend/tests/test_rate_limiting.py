import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_rate_limit_returns_429_with_headers(client: AsyncClient):
    """
    Mock the rate limiter to return count=999 (over limit) and verify
    the 429 response + rate limit headers without touching Redis.
    """
    from app.auth import rate_limiter

    async def always_limited(request, limit):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=429,
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "9999999999",
                "Retry-After": "3600",
            },
            detail={"code": "rate_limited", "message": "Rate limit exceeded. Try again later."},
        )

    # Patch on the auth router module (where check_rate_limit was imported)
    with patch("app.routers.auth.check_rate_limit", side_effect=always_limited):
        response = await client.post("/api/v1/auth/login", json={
            "email": "test@example.com", "password": "Secure123!Pass"
        })

    assert response.status_code == 429
    assert response.headers.get("X-RateLimit-Limit") == "60"
    assert response.headers.get("Retry-After") == "3600"
    assert response.json()["error"]["code"] == "rate_limited"


@pytest.mark.asyncio
async def test_rate_limit_not_triggered_normally(client: AsyncClient):
    """Normal requests are not rate limited (mock Redis to avoid infra dependency)."""
    from app.auth import rate_limiter

    # Mock _get_redis (async function) to return a fake Redis with pipeline.
    # Pipeline command stubs (zremrangebyscore, zadd, etc.) are synchronous in
    # the real client — they just queue the command; only execute() is async.
    mock_pipeline = MagicMock()
    mock_pipeline.zremrangebyscore = MagicMock()
    mock_pipeline.zadd = MagicMock()
    mock_pipeline.zcard = MagicMock()
    mock_pipeline.expire = MagicMock()
    # execute returns [removed, added, count=1, True] — count=1 is well under limit
    mock_pipeline.execute = AsyncMock(return_value=[0, 1, 1, True])

    mock_redis = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
    mock_redis.aclose = AsyncMock()

    async def fake_get_redis():
        return mock_redis

    with patch.object(rate_limiter, "_get_redis", side_effect=fake_get_redis):
        response = await client.post("/api/v1/auth/login", json={
            "email": "test@example.com", "password": "Secure123!Pass"
        })

    # 401 (wrong creds) NOT 429
    assert response.status_code == 401
