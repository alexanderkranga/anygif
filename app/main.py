"""FastAPI application — webhook endpoint, health check, lifespan."""

import logging
from contextlib import asynccontextmanager
from typing import Optional

import httpx
import redis.asyncio as aioredis
from fastapi import BackgroundTasks, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from app import config, handlers, redis as redis_mod, telegram as tg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    r = aioredis.from_url(config.get_redis_url(), decode_responses=False)
    redis_mod.set_redis(r)

    http_client = httpx.AsyncClient(timeout=60)
    tg.set_client(http_client)

    yield

    # Shutdown
    await http_client.aclose()
    await r.aclose()


app = FastAPI(title="AnyGIF Bot", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
):
    # Validate secret
    expected = config.get_webhook_secret()
    if x_telegram_bot_api_secret_token != expected:
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})

    body = await request.json()
    update = handlers.Update.model_validate(body)

    # Process in background — return 200 immediately
    background_tasks.add_task(handlers.dispatch_update, update)

    return {"ok": True}
