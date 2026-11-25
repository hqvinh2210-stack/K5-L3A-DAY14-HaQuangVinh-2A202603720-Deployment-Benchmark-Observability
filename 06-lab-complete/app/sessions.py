"""Keep recent conversation turns in Redis for all replicas."""
import json
from hashlib import sha256
from uuid import UUID

from app.redis_client import r

HISTORY_LIMIT = 20
HISTORY_TTL_SECONDS = 24 * 60 * 60


def session_key(api_key: str, session_id: UUID) -> str:
    owner = sha256(api_key.encode()).hexdigest()
    return f"day14:session:{owner}:{session_id}"


def save_turn(api_key: str, session_id: UUID, question: str, answer: str) -> None:
    key = session_key(api_key, session_id)
    turn = json.dumps({"question": question, "answer": answer}, ensure_ascii=False)
    with r.pipeline() as transaction:
        transaction.rpush(key, turn)
        transaction.ltrim(key, -HISTORY_LIMIT, -1)
        transaction.expire(key, HISTORY_TTL_SECONDS)
        transaction.execute()


def read_history(api_key: str, session_id: UUID) -> list[dict[str, str]]:
    return [json.loads(turn) for turn in r.lrange(session_key(api_key, session_id), 0, -1)]
