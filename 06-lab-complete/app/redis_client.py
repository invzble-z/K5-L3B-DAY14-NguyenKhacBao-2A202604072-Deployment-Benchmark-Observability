"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

- Đọc REDIS_URL từ config.
- Khởi tạo client non-blocking (không ping lúc import) để app vẫn khởi động khi Redis chưa sẵn sàng.
- redis_healthy() dùng cho GET /ready: trả False nhanh khi Redis không kết nối được.
"""
from typing import Optional

import redis
from redis.exceptions import RedisError

from app.config import settings


def _create_client() -> Optional[redis.Redis]:
    if not settings.redis_url:
        return None
    try:
        return redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
            retry_on_timeout=False,
        )
    except Exception:
        return None


r: Optional[redis.Redis] = _create_client()


def get_redis() -> Optional[redis.Redis]:
    """Trả về Redis client dùng chung."""
    return r


def redis_healthy() -> bool:
    """Ping Redis; trả về True nếu kết nối ổn, False nếu lỗi."""
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except (RedisError, OSError, Exception):
        return False


def close_redis() -> None:
    """Đóng connection pool sạch sẽ khi graceful shutdown."""
    client = get_redis()
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
