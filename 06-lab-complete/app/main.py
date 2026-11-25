"""
Production AI Agent — Part 6 Final Project.

Đáp ứng đủ 12 tiêu chí trong Checklist Deliverable:
  - /health (liveness) & /ready (readiness với Redis)
  - API key auth (X-API-Key → 401)
  - Stateless rate limiting (Redis sliding window → 429 + Retry-After)
  - Cost guard (Redis daily/monthly budget → 402)
  - 12-Factor config từ biến môi trường
  - Structured JSON logging
  - Graceful shutdown (lifespan + SIGTERM)
"""
import json
import logging
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, estimate_tokens, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import close_redis, redis_healthy
from utils.mock_llm import ask as llm_ask

START_TIME = time.time()


class JsonFormatter(logging.Formatter):
    """Định dạng mỗi dòng log của app thành đúng 1 JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logger() -> logging.Logger:
    app_logger = logging.getLogger("agent")
    app_logger.setLevel(getattr(logging, settings.log_level, logging.INFO))
    app_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    app_logger.addHandler(handler)
    app_logger.propagate = False
    return app_logger


logger = _configure_logger()


def _log(level: int, msg: str, **fields) -> None:
    logger.log(level, msg, extra={"extra_fields": fields})


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Đăng ký SIGTERM và chuyển tiếp lại handler gốc của uvicorn để tắt êm (exit code 0)
    prev_sigterm = signal.getsignal(signal.SIGTERM)

    def _on_sigterm(signum, frame):
        try:
            line = json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "lvl": "INFO",
                    "event": "sigterm_received",
                    "signal": signum,
                }
            ) + "\n"
            os.write(1, line.encode("utf-8"))
        except OSError:
            pass
        if callable(prev_sigterm):
            prev_sigterm(signum, frame)

    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
    except ValueError:
        pass

    _log(
        logging.INFO,
        "Agent starting up",
        event="startup",
        environment=settings.environment,
        port=settings.port,
        rate_limit_per_minute=settings.rate_limit_per_minute,
        redis_ready=redis_healthy(),
    )

    yield

    _log(
        logging.INFO,
        "Agent shutting down gracefully",
        event="shutdown",
        environment=settings.environment,
    )
    close_redis()


app = FastAPI(
    title="Production AI Agent",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    _log(
        logging.INFO,
        "HTTP request completed",
        event="request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        ms=elapsed_ms,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    _log(
        logging.ERROR,
        "Unhandled server error",
        event="unhandled_error",
        path=request.url.path,
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = Field(default=None, max_length=128)


@app.get("/health")
def health():
    """Liveness probe: luôn trả 200 khi process còn sống, không phụ thuộc Redis."""
    return {
        "status": "ok",
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 2),
    }


@app.get("/ready")
def ready():
    """Readiness probe: trả 200 khi Redis sẵn sàng, 503 khi mất kết nối Redis."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis is not ready")
    return {"status": "ready", "redis": "connected"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    rate_info = check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)

    input_tokens = estimate_tokens(body.question)
    output_tokens = estimate_tokens(answer)
    request_cost = record_cost(input_tokens, output_tokens)

    _log(
        logging.INFO,
        "LLM request processed",
        event="ask_completed",
        user_id=body.user_id or "anonymous",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=request_cost,
        rate_remaining=rate_info["remaining"],
    )

    return {
        "question": body.question,
        "answer": answer,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": request_cost,
            "rate_limit_remaining": rate_info["remaining"],
        },
    }
