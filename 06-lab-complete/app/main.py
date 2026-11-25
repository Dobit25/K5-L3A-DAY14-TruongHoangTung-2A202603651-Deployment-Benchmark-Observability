import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

from utils.mock_llm import ask as llm_ask

from .auth import verify_api_key
from .config import settings
from .cost_guard import INPUT_PRICE, OUTPUT_PRICE, check_budget, record_cost, tokens
from .rate_limiter import check_rate_limit
from .redis_client import r, redis_healthy

logger = logging.getLogger("day14.agent")
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())
logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Uvicorn drains requests before calling the lifespan shutdown hook.
    r.close()


app = FastAPI(title="Day 14 Agent", lifespan=lifespan)


@app.middleware("http")
async def log_request(request: Request, call_next):
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        logger.info(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(), "event": "request",
            "environment": settings.environment, "route": getattr(route, "path", "unmatched"),
            "status": status, "ms": round((time.perf_counter() - started) * 1000, 2),
        }))


@app.exception_handler(RedisError)
async def redis_unavailable(request: Request, exc: RedisError):
    return JSONResponse(status_code=503, content={"detail": "State store unavailable"})


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if not redis_healthy():
        raise HTTPException(503, "State store unavailable")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, key: str = Depends(verify_api_key)):
    check_rate_limit(key)
    reservation = check_budget(body.question)
    cost = 0
    try:
        answer = llm_ask(body.question)
        cost = tokens(body.question) * INPUT_PRICE + tokens(answer) * OUTPUT_PRICE
        return {"question": body.question, "answer": answer}
    finally:
        record_cost(reservation, cost)
