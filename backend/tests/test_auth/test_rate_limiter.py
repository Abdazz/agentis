import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException, Request

from app.auth.rate_limiter import check_rate_limit, rate_limit


def _make_request(user_id: str | None = "u1") -> Request:
    scope = {
        "type": "http",
        "path": "/api/v1/tasks",
        "headers": [],
        "client": ("1.2.3.4", 1234),
    }
    request = Request(scope)
    if user_id is not None:
        request.state.user_id = user_id
    return request


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    pipe = MagicMock()
    pipe.zremrangebyscore = MagicMock()
    pipe.zadd = MagicMock()
    pipe.zcard = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[0, 0, 1, True])
    r.pipeline = MagicMock(return_value=pipe)
    r.aclose = AsyncMock()
    return r, pipe


@pytest.mark.asyncio
async def test_under_limit_sets_headers_and_does_not_raise(mock_redis):
    redis, pipe = mock_redis
    pipe.execute = AsyncMock(return_value=[0, 0, 5, True])  # count=5
    with patch("app.auth.rate_limiter._get_redis", AsyncMock(return_value=redis)):
        request = _make_request()
        await check_rate_limit(request, limit=60)

    assert request.state.rate_limit_headers["X-RateLimit-Limit"] == "60"
    assert request.state.rate_limit_headers["X-RateLimit-Remaining"] == "55"
    redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_over_limit_raises_429_with_headers(mock_redis):
    redis, pipe = mock_redis
    pipe.execute = AsyncMock(return_value=[0, 0, 61, True])  # count=61 > limit=60
    with patch("app.auth.rate_limiter._get_redis", AsyncMock(return_value=redis)):
        request = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(request, limit=60)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["X-RateLimit-Remaining"] == "0"
    assert exc_info.value.headers["Retry-After"] == "3600"
    assert exc_info.value.detail["code"] == "rate_limited"


@pytest.mark.asyncio
async def test_rate_limit_key_is_scoped_per_authenticated_user(mock_redis):
    """BR-API-01: limits apply per authenticated principal, not just per IP."""
    redis, pipe = mock_redis
    with patch("app.auth.rate_limiter._get_redis", AsyncMock(return_value=redis)):
        await check_rate_limit(_make_request(user_id="user-a"), limit=60)
        await check_rate_limit(_make_request(user_id="user-b"), limit=60)

    keys_used = [call.args[0] for call in pipe.zremrangebyscore.call_args_list]
    assert any("user-a" in k for k in keys_used)
    assert any("user-b" in k for k in keys_used)


@pytest.mark.asyncio
async def test_rate_limit_dependency_delegates_to_check_rate_limit(mock_redis):
    redis, pipe = mock_redis
    pipe.execute = AsyncMock(return_value=[0, 0, 61, True])
    dependency = rate_limit(60)
    with patch("app.auth.rate_limiter._get_redis", AsyncMock(return_value=redis)):
        with pytest.raises(HTTPException) as exc_info:
            await dependency(_make_request())

    assert exc_info.value.status_code == 429
