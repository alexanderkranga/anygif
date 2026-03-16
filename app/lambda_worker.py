"""AWS Lambda handler — SQS worker for GIF generation."""

import asyncio
import json
import logging

import httpx
import redis.asyncio as aioredis

from app import config, handlers, redis as redis_mod, telegram as tg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_initialised = False


def _ensure_init():
    global _initialised
    if _initialised:
        return
    r = aioredis.from_url(config.get_redis_url(), decode_responses=False)
    redis_mod.set_redis(r)
    http_client = httpx.AsyncClient(timeout=60)
    tg.set_client(http_client)
    _initialised = True


def handler(event, context):
    _ensure_init()

    for record in event["Records"]:
        body = json.loads(record["body"])
        asyncio.run(handlers.handle_successful_payment(body["charge_id"], body["session_id"]))
