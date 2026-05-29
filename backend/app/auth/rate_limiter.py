import time
import redis.asyncio as aioredis
from fastapi import Request, HTTPException
from app.config import settings

WINDOW_SECONDS = 3600


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_cache_url, decode_responses=True)


async def check_rate_limit(request: Request, limit: int) -> None:
    """
    Sliding window rate limiter using Redis sorted sets.
    Raises HTTP 429 if the client exceeds `limit` requests in 1 hour.
    """
    # Use IP for unauthenticated; attach user_id via request.state if available
    client_id = getattr(request.state, "user_id", None) or (
        request.client.host if request.client else "unknown"
    )
    key = f"ratelimit:{client_id}:{request.url.path}"
    now = time.time()
    window_start = now - WINDOW_SECONDS

    redis = await _get_redis()
    try:
        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, WINDOW_SECONDS)
        results = await pipe.execute()
    finally:
        await redis.aclose()

    count = results[2]
    limit_int = int(limit)
    reset_at = int(now) + WINDOW_SECONDS

    if count > limit_int:
        raise HTTPException(
            status_code=429,
            headers={
                "X-RateLimit-Limit": str(limit_int),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_at),
                "Retry-After": str(WINDOW_SECONDS),
            },
            detail={"code": "rate_limited", "message": "Rate limit exceeded. Try again later."},
        )
