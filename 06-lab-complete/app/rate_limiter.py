from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException

from .config import settings
from .redis_client import r

# Redis time keeps the sliding window consistent across workers and hosts.
admit = r.register_script("""
local t = redis.call('TIME')
local now = t[1] * 1000 + math.floor(t[2] / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - 60000)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    return oldest[2] and math.max(1, math.ceil((oldest[2] + 60000 - now) / 1000)) or 60
end
redis.call('ZADD', KEYS[1], now, ARGV[2])
redis.call('EXPIRE', KEYS[1], 60)
return 0
""")


def check_rate_limit(key: str) -> None:
    fingerprint = sha256(key.encode()).hexdigest()
    retry = admit(keys=[f"day14:rate:{fingerprint}"],
                  args=[settings.rate_limit_per_minute, uuid4().hex])
    if retry:
        raise HTTPException(429, "Too many requests", headers={"Retry-After": str(retry)})
