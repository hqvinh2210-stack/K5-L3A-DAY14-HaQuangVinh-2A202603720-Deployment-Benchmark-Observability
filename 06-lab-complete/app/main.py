"""Production AI agent for the Day 14 lab."""
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from redis import RedisError

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import MOCK_RESPONSES, ask as llm_ask

logger = logging.getLogger("day14.agent")
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

# The mock uses word counts as a token estimate.
MAX_OUTPUT_TOKENS = max(
    len(answer.split()) for answers in MOCK_RESPONSES.values() for answer in answers
)


def log_event(event: str, **fields: object) -> None:
    logger.info(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "lvl": "INFO",
        "event": event,
        "environment": settings.environment,
        **fields,
    }))


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event("startup")
    try:
        yield
    finally:
        # Uvicorn drains in-flight requests before lifespan teardown.
        r.close()
        log_event("shutdown")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.middleware("http")
async def log_request(request: Request, call_next):
    started = perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        log_event(
            "request",
            method=request.method,
            path=request.url.path,
            status=status,
            ms=round((perf_counter() - started) * 1000, 2),
        )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, key: str = Depends(verify_api_key)):
    input_tokens = len(body.question.split())
    try:
        check_rate_limit(key)
        reservation = check_budget(input_tokens, MAX_OUTPUT_TOKENS)
        try:
            answer = llm_ask(body.question)
        except Exception:
            record_cost(reservation, 0, 0)
            raise
        record_cost(reservation, input_tokens, len(answer.split()))
    except RedisError as error:
        raise HTTPException(status_code=503, detail="Redis unavailable") from error
    return {"question": body.question, "answer": answer}
