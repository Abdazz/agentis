"""Redis pub/sub message bus for inter-agent communication (spec §13.2)."""
import asyncio
import json
import structlog
from typing import Any

log = structlog.get_logger()

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None  # type: ignore


class AgentTeamBus:
    """Publish sub-task results and subscribe to collect them."""

    def __init__(self, redis_url: str) -> None:
        if aioredis is None:
            raise RuntimeError("redis package not installed")
        self._redis = aioredis.from_url(redis_url, decode_responses=False)

    def _channel(self, parent_task_id: str) -> str:
        return f"agent_team:{parent_task_id}"

    async def publish(self, parent_task_id: str, message: dict[str, Any]) -> None:
        await self._redis.publish(self._channel(parent_task_id), json.dumps(message))

    async def wait_for_all(
        self,
        parent_task_id: str,
        expected_count: int,
        timeout_seconds: int = 600,
    ) -> list[dict[str, Any]]:
        """Block until `expected_count` messages arrive or timeout. Returns collected results."""
        channel = self._channel(parent_task_id)
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        results: list[dict[str, Any]] = []
        try:
            async def _collect():
                async for msg in pubsub.listen():
                    if msg.get("type") != "message":
                        continue
                    try:
                        results.append(json.loads(msg["data"]))
                    except (json.JSONDecodeError, KeyError):
                        pass
                    if len(results) >= expected_count:
                        break

            await asyncio.wait_for(_collect(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            log.warning("agent_team_bus_timeout", parent=parent_task_id, got=len(results), expected=expected_count)
        finally:
            await pubsub.unsubscribe(channel)
        return results


_bus: AgentTeamBus | None = None


def get_agent_team_bus() -> AgentTeamBus:
    global _bus
    if _bus is None:
        from app.config import settings
        _bus = AgentTeamBus(redis_url=settings.redis_cache_url)
    return _bus
