"""HITL coordinator via Redis pub/sub (spec §10 HITL-1..5)."""
import asyncio
import time
import redis
import redis.asyncio as aioredis
from app.config import settings


class HITLCoordinator:
    def __init__(self) -> None:
        self._redis_url = settings.redis_cache_url  # DB1

    def _channel(self, task_id: str) -> str:
        return f"hitl:{task_id}:response"

    async def publish_response(self, task_id: str, response: str) -> None:
        """Called by WebSocket handler when user submits HITL response."""
        r = aioredis.from_url(self._redis_url)
        try:
            await r.publish(self._channel(task_id), response)
        finally:
            await r.aclose()

    async def wait_for_response(self, task_id: str, timeout_seconds: float = 600.0) -> str | None:
        """Called by the orchestrator worker; blocks until response or timeout."""
        r = aioredis.from_url(self._redis_url)
        pubsub = r.pubsub()
        await pubsub.subscribe(self._channel(task_id))
        deadline = time.monotonic() + timeout_seconds
        try:
            while time.monotonic() < deadline:
                msg = pubsub.get_message()
                if msg and msg.get("type") == "message":
                    data = msg["data"]
                    return data.decode() if isinstance(data, bytes) else data
                await asyncio.sleep(0.5)
        finally:
            await pubsub.unsubscribe(self._channel(task_id))
            await r.aclose()
        return None


hitl_coordinator = HITLCoordinator()
