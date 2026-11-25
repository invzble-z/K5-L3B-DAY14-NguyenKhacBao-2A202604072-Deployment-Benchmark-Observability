"""
Cost guard (tiêu chí 8) — Theo dõi và chặn chi phí LLM trong Redis.

Yêu cầu:
  • Cộng dồn chi phí LLM (tính theo token) vào Redis
  • Tổng chi phí vượt DAILY_BUDGET_USD hoặc MONTHLY_BUDGET_USD → HTTP 402
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import get_redis

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

DAILY_TTL_SECONDS = 2 * 24 * 3600
MONTHLY_TTL_SECONDS = 35 * 24 * 3600


def _budget_keys() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return (
        f"cost:daily:{now.strftime('%Y-%m-%d')}",
        f"cost:monthly:{now.strftime('%Y-%m')}",
    )


def estimate_tokens(text: str) -> int:
    """Ước lượng số token đơn giản (ổn định cho mock LLM)."""
    words = len(text.split())
    return max(1, words * 2)


def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (
        output_tokens / 1000.0
    ) * PRICE_OUTPUT_PER_1K


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết ngân sách ngày hoặc tháng → raise HTTPException(402)."""
    client = get_redis()
    if client is None:
        raise HTTPException(status_code=503, detail="Cost guard storage unavailable")

    daily_key, monthly_key = _budget_keys()
    try:
        raw_daily, raw_monthly = client.mget(daily_key, monthly_key)
        daily_spent = float(raw_daily or 0.0)
        monthly_spent = float(raw_monthly or 0.0)
    except (RedisError, OSError, ValueError):
        raise HTTPException(status_code=503, detail="Cost guard storage unavailable")

    if daily_spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Daily LLM budget exceeded "
                f"(spent=${daily_spent:.6f} >= limit=${settings.daily_budget_usd:.6f})"
            ),
        )

    if monthly_spent >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Monthly LLM budget exceeded "
                f"(spent=${monthly_spent:.6f} >= limit=${settings.monthly_budget_usd:.6f})"
            ),
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí vào tổng ngày & tháng trong Redis, trả về chi phí request."""
    cost = calculate_cost(input_tokens, output_tokens)
    client = get_redis()
    if client is None:
        return cost

    daily_key, monthly_key = _budget_keys()
    try:
        pipe = client.pipeline(transaction=True)
        pipe.incrbyfloat(daily_key, cost)
        pipe.expire(daily_key, DAILY_TTL_SECONDS)
        pipe.incrbyfloat(monthly_key, cost)
        pipe.expire(monthly_key, MONTHLY_TTL_SECONDS)
        pipe.execute()
    except (RedisError, OSError):
        pass
    return round(cost, 8)
