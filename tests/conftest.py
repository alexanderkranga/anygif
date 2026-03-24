"""Shared test fixtures — fake Redis, mock Telegram API."""

from __future__ import annotations

import os
import pytest
import pytest_asyncio
import fakeredis
# Set required env vars before any app imports
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-bot-token")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("GENERATION_PRICE_STARS", "10")
os.environ.setdefault("SESSION_TTL_SECONDS", "120")
os.environ.setdefault("FREE_MODE", "false")

from app import redis as redis_mod


@pytest_asyncio.fixture
async def fake_redis():
    """Provide a fresh fakeredis instance for each test."""
    server = fakeredis.FakeServer()
    r = fakeredis.FakeAsyncRedis(server=server)
    redis_mod.set_redis(r)
    yield r
    await r.aclose()


class _TelegramCallTracker(list):
    """List subclass that also stores custom response overrides."""
    def __init__(self):
        super().__init__()
        self._responses = {}

    def set_response(self, method, resp):
        self._responses[method] = resp


@pytest.fixture
def telegram_calls():
    """Track all Telegram API calls made during a test.

    Returns a list that accumulates (method, kwargs) tuples.
    Patches the telegram module's _call function.
    """
    calls = _TelegramCallTracker()

    async def mock_call(method: str, **kwargs):
        calls.append((method, kwargs))
        if method in calls._responses:
            return calls._responses[method]
        if method == "sendMessage":
            return {"ok": True, "result": {"message_id": 9999}}
        if method == "sendInvoice":
            return {"ok": True, "result": {"message_id": 9998}}
        if method == "deleteMessage":
            return {"ok": True}
        if method == "sendDocument":
            return {"ok": True, "result": {"message_id": 9997}}
        if method == "sendAnimation":
            return {"ok": True, "result": {"message_id": 9996}}
        if method == "answerPreCheckoutQuery":
            return {"ok": True}
        if method == "refundStarPayment":
            return {"ok": True}
        return {"ok": True}

    import app.telegram as tg_mod
    original = tg_mod._call
    tg_mod._call = mock_call
    yield calls
    tg_mod._call = original


