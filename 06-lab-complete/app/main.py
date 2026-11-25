"""Production AI agent for the Day 14 lab."""
import json
import logging
from asyncio import sleep
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from redis import RedisError

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from app.sessions import read_history, save_turn
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
    session_id: UUID | None = None


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


def generate_answer(body: AskRequest, key: str) -> str:
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
        if body.session_id is not None:
            save_turn(key, body.session_id, body.question, answer)
    except RedisError as error:
        raise HTTPException(status_code=503, detail="Redis unavailable") from error
    return answer


@app.post("/ask")
def ask(body: AskRequest, key: str = Depends(verify_api_key)):
    response = {"question": body.question, "answer": generate_answer(body, key)}
    if body.session_id is not None:
        response["session_id"] = str(body.session_id)
    return response


async def stream_mock_answer(answer: str):
    for index, word in enumerate(answer.split(" ")):
        await sleep(0.05)
        yield word if index == 0 else " " + word


@app.post("/ask/stream")
def ask_stream(body: AskRequest, key: str = Depends(verify_api_key)):
    answer = generate_answer(body, key)
    return StreamingResponse(stream_mock_answer(answer), media_type="text/plain")


@app.get("/sessions/{session_id}")
def get_session(session_id: UUID, key: str = Depends(verify_api_key)):
    try:
        check_rate_limit(key)
        history = read_history(key, session_id)
    except RedisError as error:
        raise HTTPException(status_code=503, detail="Redis unavailable") from error
    return {"session_id": str(session_id), "history": history}
