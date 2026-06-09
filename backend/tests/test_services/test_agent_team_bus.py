import pytest, asyncio, json
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_publish_sends_to_channel():
    fake_redis = MagicMock()
    fake_redis.publish = AsyncMock(return_value=1)
    with patch("app.services.agent_team_bus.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = fake_redis
        from app.services.agent_team_bus import AgentTeamBus
        bus = AgentTeamBus(redis_url="redis://localhost:6379/1")
        await bus.publish("parent-123", {"subtask_id": "child-456", "result": "done"})
        fake_redis.publish.assert_called_once()
        channel, payload = fake_redis.publish.call_args[0]
        assert channel == "agent_team:parent-123"
        assert json.loads(payload)["subtask_id"] == "child-456"


@pytest.mark.asyncio
async def test_channel_format():
    fake_redis = MagicMock()
    with patch("app.services.agent_team_bus.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = fake_redis
        from app.services.agent_team_bus import AgentTeamBus
        bus = AgentTeamBus(redis_url="redis://localhost:6379/1")
        assert bus._channel("abc-123") == "agent_team:abc-123"
