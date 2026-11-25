"""
Rate limiting (tiêu chí 7) — Sliding window 60 giây lưu trong Redis.

Yêu cầu:
  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây
  • Vượt giới hạn → HTTP 429 kèm header Retry-After
  • State lưu trong Redis (stateless) để mọi worker dùng chung và bền qua restart
"""
import math
import time
import uuid

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import get_redis

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> dict:
    """Kiểm tra và ghi nhận request theo thuật toán sliding window trên Redis Sorted Set."""
    client = get_redis()
    if client is None:
        raise HTTPException(status_code=503, detail="Rate limiter storage unavailable")

    limit = settings.rate_limit_per_minute
    now = time.time()
    window_start = now - WINDOW_SECONDS
    redis_key = f"ratelimit:{key}"

    try:
        pipe = client.pipeline(transaction=True)
        pipe.zremrangebyscore(redis_key, "-inf", window_start)
        pipe.zcard(redis_key)
        pipe.zrange(redis_key, 0, 0, withscores=True)
        _, current_count, oldest_entries = pipe.execute()

        if current_count >= limit:
            retry_after = WINDOW_SECONDS
            if oldest_entries:
                oldest_ts = float(oldest_entries[0][1])
                retry_after = max(1, int(math.ceil(oldest_ts + WINDOW_SECONDS - now)))
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({limit} requests per {WINDOW_SECONDS}s)",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        member = f"{now:.6f}:{uuid.uuid4().hex}"
        pipe = client.pipeline(transaction=True)
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS * 2)
        pipe.execute()

        remaining = max(0, limit - current_count - 1)
        return {"limit": limit, "remaining": remaining}
    except HTTPException:
        raise
    except (RedisError, OSError):
        raise HTTPException(status_code=503, detail="Rate limiter storage unavailable")
