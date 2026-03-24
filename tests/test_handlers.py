"""Tests for command handlers — /gif validation, /start, /help."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.handlers import dispatch_update
from app.models import Update


class TestGifCommand:
    @pytest.mark.asyncio
    async def test_missing_params(self, fake_redis, telegram_calls):
        update = Update(
            update_id=1,
            message={"message_id": 1, "chat": {"id": 100}, "from": {"id": 1}, "text": "/gif"},
        )
        await dispatch_update(update)

        send_calls = [(m, kw) for m, kw in telegram_calls if m == "sendMessage"]
        assert len(send_calls) == 1
        assert "3 parameters" in send_calls[0][1]["json"]["text"]

    @pytest.mark.asyncio
    async def test_invalid_start_time(self, fake_redis, telegram_calls):
        update = Update(
            update_id=1,
            message={"message_id": 1, "chat": {"id": 100}, "from": {"id": 1},
                      "text": "/gif https://example.com abc 5"},
        )
        await dispatch_update(update)

        send_calls = [(m, kw) for m, kw in telegram_calls if m == "sendMessage"]
        assert len(send_calls) == 1
        assert "Invalid start time" in send_calls[0][1]["json"]["text"]

    @pytest.mark.asyncio
    async def test_invalid_duration_not_integer(self, fake_redis, telegram_calls):
        update = Update(
            update_id=1,
            message={"message_id": 1, "chat": {"id": 100}, "from": {"id": 1},
                      "text": "/gif https://example.com 1:30 abc"},
        )
        await dispatch_update(update)

        send_calls = [(m, kw) for m, kw in telegram_calls if m == "sendMessage"]
        assert len(send_calls) == 1
        assert "integer" in send_calls[0][1]["json"]["text"].lower()

    @pytest.mark.asyncio
    async def test_duration_out_of_range(self, fake_redis, telegram_calls):
        update = Update(
            update_id=1,
            message={"message_id": 1, "chat": {"id": 100}, "from": {"id": 1},
                      "text": "/gif https://example.com 1:30 15"},
        )
        await dispatch_update(update)

        send_calls = [(m, kw) for m, kw in telegram_calls if m == "sendMessage"]
        assert len(send_calls) == 1
        assert "1 and 10" in send_calls[0][1]["json"]["text"]

    @pytest.mark.asyncio
    async def test_duration_zero_rejected(self, fake_redis, telegram_calls):
        update = Update(
            update_id=1,
            message={"message_id": 1, "chat": {"id": 100}, "from": {"id": 1},
                      "text": "/gif https://example.com 1:30 0"},
        )
        await dispatch_update(update)

        send_calls = [(m, kw) for m, kw in telegram_calls if m == "sendMessage"]
        assert len(send_calls) == 1
        assert "1 and 10" in send_calls[0][1]["json"]["text"]

    @pytest.mark.asyncio
    async def test_valid_gif_command_sends_invoice(self, fake_redis, telegram_calls):
        update = Update(
            update_id=1,
            message={"message_id": 1, "chat": {"id": 100}, "from": {"id": 1},
                      "text": "/gif https://youtube.com/watch?v=abc 1:30 5"},
        )
        await dispatch_update(update)

        invoice_calls = [(m, kw) for m, kw in telegram_calls if m == "sendInvoice"]
        assert len(invoice_calls) == 1
        assert invoice_calls[0][1]["json"]["currency"] == "XTR"

    @pytest.mark.asyncio
    async def test_valid_gif_command_creates_session(self, fake_redis, telegram_calls):
        from app import redis as redis_mod
        update = Update(
            update_id=1,
            message={"message_id": 1, "chat": {"id": 100}, "from": {"id": 1},
                      "text": "/gif https://youtube.com/watch?v=abc 0:00 10"},
        )
        await dispatch_update(update)

        # Invoice was sent, extract session_id from payload
        invoice_calls = [(m, kw) for m, kw in telegram_calls if m == "sendInvoice"]
        session_id = invoice_calls[0][1]["json"]["payload"]
        session = await redis_mod.get_session(session_id)
        assert session is not None
        assert session.video_url == "https://youtube.com/watch?v=abc"
        assert session.start_time == "0:00"
        assert session.duration == 10


class TestStartHelp:
    @pytest.mark.asyncio
    async def test_start_command(self, fake_redis, telegram_calls):
        update = Update(
            update_id=1,
            message={"message_id": 1, "chat": {"id": 100}, "from": {"id": 1}, "text": "/start"},
        )
        await dispatch_update(update)

        send_calls = [(m, kw) for m, kw in telegram_calls if m == "sendMessage"]
        assert len(send_calls) == 1
        assert "AnyGif" in send_calls[0][1]["json"]["text"]

    @pytest.mark.asyncio
    async def test_help_command(self, fake_redis, telegram_calls):
        update = Update(
            update_id=1,
            message={"message_id": 1, "chat": {"id": 100}, "from": {"id": 1}, "text": "/help"},
        )
        await dispatch_update(update)

        send_calls = [(m, kw) for m, kw in telegram_calls if m == "sendMessage"]
        assert len(send_calls) == 1
        assert "Usage" in send_calls[0][1]["json"]["text"]


class TestFreeMode:
    @pytest.mark.asyncio
    async def test_start_command_free_mode_shows_free_text(self, fake_redis, telegram_calls, monkeypatch):
        monkeypatch.setenv("FREE_MODE", "true")
        update = Update(
            update_id=1,
            message={"message_id": 1, "chat": {"id": 100}, "from": {"id": 1}, "text": "/start"},
        )
        await dispatch_update(update)

        send_calls = [(m, kw) for m, kw in telegram_calls if m == "sendMessage"]
        assert len(send_calls) == 1
        assert "FREE" in send_calls[0][1]["json"]["text"]
        assert send_calls[0][1]["json"].get("parse_mode") == "HTML"

    @pytest.mark.asyncio
    async def test_help_command_free_mode(self, fake_redis, telegram_calls, monkeypatch):
        monkeypatch.setenv("FREE_MODE", "true")
        update = Update(
            update_id=1,
            message={"message_id": 1, "chat": {"id": 100}, "from": {"id": 1}, "text": "/help"},
        )
        await dispatch_update(update)

        send_calls = [(m, kw) for m, kw in telegram_calls if m == "sendMessage"]
        assert len(send_calls) == 1
        assert "free" in send_calls[0][1]["json"]["text"].lower()

    @pytest.mark.asyncio
    async def test_gif_command_free_mode_enqueues_directly(self, fake_redis, telegram_calls, monkeypatch):
        monkeypatch.setenv("FREE_MODE", "true")
        mock_enqueue = MagicMock()
        monkeypatch.setattr("app.handlers.queue.enqueue_generation", mock_enqueue)

        update = Update(
            update_id=1,
            message={"message_id": 1, "chat": {"id": 100}, "from": {"id": 1},
                      "text": "/gif https://youtube.com/watch?v=abc 1:30 5"},
        )
        await dispatch_update(update)

        # No invoice should be sent
        invoice_calls = [(m, kw) for m, kw in telegram_calls if m == "sendInvoice"]
        assert len(invoice_calls) == 0

        # Should enqueue directly
        assert mock_enqueue.call_count == 1
        args = mock_enqueue.call_args[0]
        assert args[0].startswith("free-")  # synthetic charge_id

    @pytest.mark.asyncio
    async def test_gif_command_paid_mode_sends_invoice(self, fake_redis, telegram_calls, monkeypatch):
        monkeypatch.setenv("FREE_MODE", "false")
        update = Update(
            update_id=1,
            message={"message_id": 1, "chat": {"id": 100}, "from": {"id": 1},
                      "text": "/gif https://youtube.com/watch?v=abc 1:30 5"},
        )
        await dispatch_update(update)

        invoice_calls = [(m, kw) for m, kw in telegram_calls if m == "sendInvoice"]
        assert len(invoice_calls) == 1
