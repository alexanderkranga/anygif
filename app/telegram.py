"""Thin async Telegram Bot API client using httpx."""

from __future__ import annotations

import io
import logging
from typing import Any, Optional

import httpx

from app.config import get_bot_token

logger = logging.getLogger(__name__)

BASE_URL = "https://api.telegram.org"

# Shared httpx client — set during app lifespan
_client: Optional[httpx.AsyncClient] = None


def set_client(client: httpx.AsyncClient) -> None:
    global _client
    _client = client


def get_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("httpx client not initialised")
    return _client


def _url(method: str) -> str:
    return f"{BASE_URL}/bot{get_bot_token()}/{method}"


async def _call(method: str, **kwargs: Any) -> dict:
    client = get_client()
    resp = await client.post(_url(method), **kwargs)
    data = resp.json()
    if not data.get("ok"):
        logger.error("Telegram API error on %s: error_code=%s", method, data.get("error_code"))
    return data


# ── Messaging ───────────────────────────────────────────────────────

async def send_message(
    chat_id: int,
    text: str,
    reply_to_message_id: Optional[int] = None,
    parse_mode: Optional[str] = None,
) -> dict:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id
    if parse_mode is not None:
        payload["parse_mode"] = parse_mode
    return await _call("sendMessage", json=payload)


async def delete_message(chat_id: int, message_id: int) -> dict:
    return await _call("deleteMessage", json={
        "chat_id": chat_id,
        "message_id": message_id,
    })


async def send_document(
    chat_id: int,
    file_bytes: bytes,
    filename: str,
    reply_to_message_id: Optional[int] = None,
    mime_type: str = "image/gif",
) -> dict:
    files = {"document": (filename, io.BytesIO(file_bytes), mime_type)}
    data: dict[str, Any] = {"chat_id": str(chat_id)}
    if reply_to_message_id is not None:
        data["reply_to_message_id"] = str(reply_to_message_id)
    return await _call("sendDocument", data=data, files=files)


async def send_animation(
    chat_id: int,
    file_bytes: bytes,
    filename: str,
    reply_to_message_id: Optional[int] = None,
) -> dict:
    files = {"animation": (filename, io.BytesIO(file_bytes), "video/mp4")}
    data: dict[str, Any] = {"chat_id": str(chat_id)}
    if reply_to_message_id is not None:
        data["reply_to_message_id"] = str(reply_to_message_id)
    return await _call("sendAnimation", data=data, files=files)


# ── Payments ────────────────────────────────────────────────────────

async def send_invoice(
    chat_id: int,
    title: str,
    description: str,
    payload: str,
    currency: str,
    prices: list[dict[str, Any]],
    reply_to_message_id: Optional[int] = None,
) -> dict:
    data: dict[str, Any] = {
        "chat_id": chat_id,
        "title": title,
        "description": description,
        "payload": payload,
        "currency": currency,
        "prices": prices,
    }
    if reply_to_message_id is not None:
        data["reply_to_message_id"] = reply_to_message_id
    return await _call("sendInvoice", json=data)


async def answer_pre_checkout_query(
    pre_checkout_query_id: str,
    ok: bool,
    error_message: Optional[str] = None,
) -> dict:
    data: dict[str, Any] = {
        "pre_checkout_query_id": pre_checkout_query_id,
        "ok": ok,
    }
    if error_message is not None:
        data["error_message"] = error_message
    return await _call("answerPreCheckoutQuery", json=data)


async def refund_star_payment(user_id: int, telegram_payment_charge_id: str) -> dict:
    return await _call("refundStarPayment", json={
        "user_id": user_id,
        "telegram_payment_charge_id": telegram_payment_charge_id,
    })
