"""Reserve budget before calling the mock and reconcile the actual cost."""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

NANO_USD_PER_USD = 10**9
INPUT_NANO_USD_PER_TOKEN = 150
OUTPUT_NANO_USD_PER_TOKEN = 600
DAILY_BUDGET = int(Decimal(settings.daily_budget_usd) * NANO_USD_PER_USD)

reserve_budget = r.register_script("""
local spent = tonumber(redis.call('GET', KEYS[1]) or '0')
local reservation = tonumber(ARGV[1])
if spent + reservation > tonumber(ARGV[2]) then
    return 0
end
redis.call('INCRBY', KEYS[1], reservation)
redis.call('EXPIRE', KEYS[1], 172800, 'NX')
return 1
""")

release_unused = r.register_script("""
if redis.call('EXISTS', KEYS[1]) == 1 then
    redis.call('DECRBY', KEYS[1], ARGV[1])
end
""")


def check_budget(input_tokens: int, max_output_tokens: int) -> tuple[str, int]:
    day = datetime.now(timezone.utc).date().isoformat()
    key = f"day14:cost:{day}"
    maximum = (
        input_tokens * INPUT_NANO_USD_PER_TOKEN
        + max_output_tokens * OUTPUT_NANO_USD_PER_TOKEN
    )
    if not reserve_budget(keys=[key], args=[maximum, DAILY_BUDGET]):
        raise HTTPException(status_code=402, detail="Daily budget exhausted")
    return key, maximum


def record_cost(reservation: tuple[str, int], input_tokens: int, output_tokens: int) -> None:
    key, maximum = reservation
    actual = input_tokens * INPUT_NANO_USD_PER_TOKEN + output_tokens * OUTPUT_NANO_USD_PER_TOKEN
    release_unused(keys=[key], args=[maximum - actual])
