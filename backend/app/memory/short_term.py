"""Short-term memory (Feature MEM-2). Redis DB1, 24h TTL, scoped per user."""
import redis.asyncio as aioredis
from app.config import settings
from app.orchestrator.context import count_tokens

_TTL_24H = 86_400
_MAX_RECENT = 20


class ShortTermMemory:
    def __init__(self):
        self._redis = aioredis.from_url(settings.redis_cache_url, decode_responses=True)

    def _recent_key(self, user_id: str) -> str:
        return f"mem:short:{user_id}:recent"

    def _prefs_key(self, user_id: str) -> str:
        return f"mem:short:{user_id}:prefs"

    async def store_task_summary(self, user_id: str, summary: str) -> None:
        key = self._recent_key(user_id)
        await self._redis.lpush(key, summary)
        await self._redis.ltrim(key, 0, _MAX_RECENT - 1)
        await self._redis.expire(key, _TTL_24H)

    async def get_recent_summaries(self, user_id: str) -> list[str]:
        return await self._redis.lrange(self._recent_key(user_id), 0, _MAX_RECENT - 1)

    async def store_pref(self, user_id: str, name: str, value: str) -> None:
        key = self._prefs_key(user_id)
        await self._redis.hset(key, name, value)
        await self._redis.expire(key, _TTL_24H)

    async def get_prefs(self, user_id: str) -> dict[str, str]:
        return await self._redis.hgetall(self._prefs_key(user_id))

    async def build_context_block(self, user_id: str, max_tokens: int = 500) -> str:
        """Assemble a short-term memory block for the system prompt (BR-MEM-12),
        capped at max_tokens."""
        prefs = await self.get_prefs(user_id)
        recent = await self.get_recent_summaries(user_id)
        lines: list[str] = []
        if prefs:
            lines.append("User preferences: " + "; ".join(f"{k}={v}" for k, v in prefs.items()))
        block = ""
        for summary in recent:
            candidate = block + f"- {summary}\n"
            header = "\n".join(lines)
            if count_tokens(header + "\nRecent tasks:\n" + candidate) > max_tokens:
                break
            block = candidate
        parts = []
        if lines:
            parts.append("\n".join(lines))
        if block:
            parts.append("Recent tasks:\n" + block.rstrip())
        return "\n".join(parts)

    async def clear(self, user_id: str) -> None:
        await self._redis.delete(self._recent_key(user_id), self._prefs_key(user_id))

    async def close(self) -> None:
        await self._redis.aclose()
