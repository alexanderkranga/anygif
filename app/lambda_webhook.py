"""AWS Lambda handler — webhook entrypoint (fast path)."""

import asyncio
import json
import logging
import os

import boto3
import httpx
import redis.asyncio as aioredis

from app import config, handlers, redis as redis_mod, stats, telegram as tg
from app.models import Update

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_initialised = False
_sqs = None


def _ensure_init():
    global _initialised, _sqs
    if _initialised:
        return
    r = aioredis.from_url(config.get_redis_url(), decode_responses=False)
    redis_mod.set_redis(r)
    http_client = httpx.AsyncClient(timeout=60)
    tg.set_client(http_client)
    _sqs = boto3.client("sqs")
    _initialised = True


def handler(event, context):
    _ensure_init()

    ctx_http = event.get("requestContext", {}).get("http", {})
    if ctx_http.get("method") == "GET" and ctx_http.get("path") == "/stats":
        count = stats.get_gif_count()
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "https://anygifbot.com",
                "Cache-Control": "public, max-age=60",
                "X-Content-Type-Options": "nosniff",
            },
            "body": json.dumps({"count": count}),
        }

    headers = event.get("headers") or {}
    secret = headers.get("x-telegram-bot-api-secret-token")

    if secret != config.get_webhook_secret():
        return {"statusCode": 403, "body": '{"detail": "Forbidden"}'}

    body = json.loads(event.get("body", "{}"))
    update = Update.model_validate(body)

    # Offload payment processing to SQS worker
    if (
        update.message is not None
        and update.message.successful_payment is not None
    ):
        payment = update.message.successful_payment
        charge_id = payment.telegram_payment_charge_id
        session_id = payment.invoice_payload

        user_id = update.message.from_.id if update.message.from_ else 0
        asyncio.run(redis_mod.save_refund_fallback(session_id, user_id))

        minimal_payload = json.dumps({"charge_id": charge_id, "session_id": session_id})
        queue_url = os.environ["SQS_QUEUE_URL"]
        _sqs.send_message(QueueUrl=queue_url, MessageBody=minimal_payload)
        return {"statusCode": 200, "body": '{"ok": true}'}

    # Fast-path: commands, pre_checkout, everything else
    asyncio.run(handlers.dispatch_update(update))
    return {"statusCode": 200, "body": '{"ok": true}'}
