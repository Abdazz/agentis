import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.publish = AsyncMock(return_value=1)
    r.aclose = AsyncMock()
    pubsub = AsyncMock()
    pubsub.subscribe = AsyncMock()
    pubsub.get_message = MagicMock(return_value=None)
    pubsub.unsubscribe = AsyncMock()
    r.pubsub = MagicMock(return_value=pubsub)
    return r


@pytest.mark.asyncio
async def test_publish_response_sends_to_correct_channel(mock_redis):
    with patch("app.services.hitl.redis.asyncio.from_url", return_value=mock_redis):
        from app.services import hitl as hitl_module
        import importlib
        importlib.reload(hitl_module)
        from app.services.hitl import HITLCoordinator
        coord = HITLCoordinator()
        await coord.publish_response(task_id="t1", response="yes, proceed")
        mock_redis.publish.assert_called_once_with("hitl:t1:response", "yes, proceed")


@pytest.mark.asyncio
async def test_wait_for_response_returns_message(mock_redis):
    mock_redis.pubsub.return_value.get_message = MagicMock(
        return_value={"type": "message", "data": b"ok"}
    )
    with patch("app.services.hitl.redis.asyncio.from_url", return_value=mock_redis):
        from app.services.hitl import HITLCoordinator
        coord = HITLCoordinator()
        result = await coord.wait_for_response(task_id="t1", timeout_seconds=5)
        assert result == "ok"


@pytest.mark.asyncio
async def test_wait_for_response_returns_none_on_timeout(mock_redis):
    mock_redis.pubsub.return_value.get_message = MagicMock(return_value=None)
    with patch("app.services.hitl.redis.asyncio.from_url", return_value=mock_redis):
        with patch("app.services.hitl.asyncio.sleep", AsyncMock()):
            from app.services.hitl import HITLCoordinator
            coord = HITLCoordinator()
            result = await coord.wait_for_response(task_id="t1", timeout_seconds=0)
            assert result is None
