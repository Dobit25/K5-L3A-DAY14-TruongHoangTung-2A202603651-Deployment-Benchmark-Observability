from datetime import datetime, timezone

from fastapi import HTTPException

from utils.mock_llm import MOCK_RESPONSES

from .config import settings
from .redis_client import r

# Integer nano-USD per token (the mock estimates one token per four characters).
INPUT_PRICE = 150
OUTPUT_PRICE = 600
NANO_USD = 10**9


def tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


MAX_OUTPUT = max(tokens(text) for choices in MOCK_RESPONSES.values() for text in choices)
reserve = r.register_script("""
local amount = tonumber(ARGV[1])
for i = 1, 2 do
    if tonumber(redis.call('GET', KEYS[i]) or 0) + amount > tonumber(ARGV[i+1]) then
        return 0
    end
end
for i = 1, 2 do
    redis.call('INCRBY', KEYS[i], amount)
    redis.call('EXPIRE', KEYS[i], tonumber(ARGV[i+3]))
end
return 1
""")


def check_budget(question: str) -> tuple[list[str], int]:
    now = datetime.now(timezone.utc)
    keys = [f"day14:cost:{now:%Y-%m-%d}", f"day14:cost:{now:%Y-%m}"]
    maximum = tokens(question) * INPUT_PRICE + MAX_OUTPUT * OUTPUT_PRICE
    limits = [int(settings.daily_budget_usd * NANO_USD), int(settings.monthly_budget_usd * NANO_USD)]
    if not reserve(keys=keys, args=[maximum, *limits, 2 * 86400, 32 * 86400]):
        raise HTTPException(402, "LLM budget exhausted")
    return keys, maximum


def record_cost(reservation: tuple[list[str], int], actual: int) -> None:
    keys, maximum = reservation
    with r.pipeline(transaction=True) as transaction:
        for key in keys:
            transaction.incrby(key, actual - maximum)
        transaction.execute()
