"""Tests for the full payment flow — pre_checkout, successful_payment, refunds."""

import time
import pytest
from unittest.mock import patch, AsyncMock

from app import redis as redis_mod
from app.handlers import handle_pre_checkout, handle_successful_payment, dispatch_update
from app.models import (
    Update, Message, Chat, TelegramUser, PreCheckoutQuery,
    SuccessfulPayment, Session,
)


def _make_session(session_id: str = "sess-123", **overrides) -> Session:
    defaults = dict(
        session_id=session_id,
        user_id=1,
        chat_id=100,
        original_message_id=10,
        video_url="https://youtube.com/watch?v=abc123",
        start_time="1:30",
        duration=5,
        expires_at=time.time() + 600,
    )
    defaults.update(overrides)
    return Session(**defaults)


class TestPreCheckout:
    @pytest.mark.asyncio
    async def test_valid_session_answers_ok(self, fake_redis, telegram_calls):
        session = _make_session()
        await redis_mod.save_session(session)

        query = PreCheckoutQuery(
            id="query-1",
            from_=TelegramUser(id=1),
            currency="XTR",
            total_amount=1,
            invoice_payload="sess-123",
        )
        await handle_pre_checkout(query)

        answer_calls = [(m, kw) for m, kw in telegram_calls if m == "answerPreCheckoutQuery"]
        assert len(answer_calls) == 1
        assert answer_calls[0][1]["json"]["ok"] is True

    @pytest.mark.asyncio
    async def test_expired_session_answers_not_ok(self, fake_redis, telegram_calls):
        query = PreCheckoutQuery(
            id="query-2",
            from_=TelegramUser(id=1),
            currency="XTR",
            total_amount=1,
            invoice_payload="sess-nonexistent",
        )
        await handle_pre_checkout(query)

        answer_calls = [(m, kw) for m, kw in telegram_calls if m == "answerPreCheckoutQuery"]
        assert len(answer_calls) == 1
        assert answer_calls[0][1]["json"]["ok"] is False
        assert "expired" in answer_calls[0][1]["json"]["error_message"].lower()

    @pytest.mark.asyncio
    async def test_pre_checkout_dispatched_from_update(self, fake_redis, telegram_calls):
        session = _make_session()
        await redis_mod.save_session(session)

        update = Update(
            update_id=1,
            pre_checkout_query={
                "id": "q1",
                "from": {"id": 1},
                "currency": "XTR",
                "total_amount": 1,
                "invoice_payload": "sess-123",
            },
        )
        await dispatch_update(update)

        answer_calls = [(m, kw) for m, kw in telegram_calls if m == "answerPreCheckoutQuery"]
        assert len(answer_calls) == 1
        assert answer_calls[0][1]["json"]["ok"] is True


class TestSuccessfulPayment:
    @pytest.mark.asyncio
    async def test_successful_generation_delivers_gif(self, fake_redis, telegram_calls):
        session = _make_session(invoice_message_id=9998)
        await redis_mod.save_session(session)

        msg = Message(
            message_id=20,
            chat=Chat(id=100),
            from_=TelegramUser(id=1),
            successful_payment=SuccessfulPayment(
                currency="XTR",
                total_amount=1,
                invoice_payload="sess-123",
                telegram_payment_charge_id="charge-1",
            ),
        )

        with patch("app.handlers.gif.generate_gif", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = b"fake-gif-bytes"
            await handle_successful_payment(msg)

        # Should send "Generating..." then delete it, then send document
        send_calls = [(m, kw) for m, kw in telegram_calls if m == "sendMessage"]
        assert any("Generating" in kw["json"]["text"] for _, kw in send_calls)

        doc_calls = [(m, kw) for m, kw in telegram_calls if m == "sendAnimation"]
        assert len(doc_calls) == 1

        # Two deletes: invoice message + "Generating..." message
        delete_calls = [(m, kw) for m, kw in telegram_calls if m == "deleteMessage"]
        assert len(delete_calls) == 2
        deleted_ids = {kw["json"]["message_id"] for _, kw in delete_calls}
        assert 9998 in deleted_ids  # invoice

        # No refund
        refund_calls = [(m, kw) for m, kw in telegram_calls if m == "refundStarPayment"]
        assert len(refund_calls) == 0

        # Session should be cleaned up
        assert await redis_mod.get_session("sess-123") is None

    @pytest.mark.asyncio
    async def test_invoice_message_id_none_no_extra_delete(self, fake_redis, telegram_calls):
        session = _make_session(invoice_message_id=None)
        await redis_mod.save_session(session)

        msg = Message(
            message_id=20,
            chat=Chat(id=100),
            from_=TelegramUser(id=1),
            successful_payment=SuccessfulPayment(
                currency="XTR",
                total_amount=1,
                invoice_payload="sess-123",
                telegram_payment_charge_id="charge-noinvoiceid",
            ),
        )

        with patch("app.handlers.gif.generate_gif", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = b"fake-gif-bytes"
            await handle_successful_payment(msg)

        # Only one delete: the "Generating..." message
        delete_calls = [(m, kw) for m, kw in telegram_calls if m == "deleteMessage"]
        assert len(delete_calls) == 1

    @pytest.mark.asyncio
    async def test_duplicate_payment_ignored(self, fake_redis, telegram_calls):
        session = _make_session()
        await redis_mod.save_session(session)

        msg = Message(
            message_id=20,
            chat=Chat(id=100),
            from_=TelegramUser(id=1),
            successful_payment=SuccessfulPayment(
                currency="XTR",
                total_amount=1,
                invoice_payload="sess-123",
                telegram_payment_charge_id="charge-dup",
            ),
        )

        # First call
        with patch("app.handlers.gif.generate_gif", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = b"fake-gif"
            await handle_successful_payment(msg)

        calls_after_first = len(telegram_calls)

        # Second call with same charge_id
        with patch("app.handlers.gif.generate_gif", new_callable=AsyncMock) as mock_gen:
            await handle_successful_payment(msg)
            # generate_gif should NOT be called
            mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_session_at_payment_triggers_refund(self, fake_redis, telegram_calls):
        msg = Message(
            message_id=20,
            chat=Chat(id=100),
            from_=TelegramUser(id=1),
            successful_payment=SuccessfulPayment(
                currency="XTR",
                total_amount=1,
                invoice_payload="sess-gone",
                telegram_payment_charge_id="charge-nosess",
            ),
        )

        await handle_successful_payment(msg)

        refund_calls = [(m, kw) for m, kw in telegram_calls if m == "refundStarPayment"]
        assert len(refund_calls) == 1
        assert refund_calls[0][1]["json"]["telegram_payment_charge_id"] == "charge-nosess"

        send_calls = [(m, kw) for m, kw in telegram_calls if m == "sendMessage"]
        assert any("refunded" in kw["json"]["text"].lower() for _, kw in send_calls)

    @pytest.mark.asyncio
    async def test_generation_error_refunds(self, fake_redis, telegram_calls):
        session = _make_session()
        await redis_mod.save_session(session)

        msg = Message(
            message_id=20,
            chat=Chat(id=100),
            from_=TelegramUser(id=1),
            successful_payment=SuccessfulPayment(
                currency="XTR",
                total_amount=1,
                invoice_payload="sess-123",
                telegram_payment_charge_id="charge-fail",
            ),
        )

        with patch("app.handlers.gif.generate_gif", new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = Exception("ffmpeg crashed")
            await handle_successful_payment(msg)

        refund_calls = [(m, kw) for m, kw in telegram_calls if m == "refundStarPayment"]
        assert len(refund_calls) == 1

        send_calls = [(m, kw) for m, kw in telegram_calls if m == "sendMessage"]
        assert any("failed" in kw["json"]["text"].lower() for _, kw in send_calls)

    @pytest.mark.asyncio
    async def test_payment_dispatched_from_update(self, fake_redis, telegram_calls):
        session = _make_session()
        await redis_mod.save_session(session)

        update = Update(
            update_id=1,
            message={
                "message_id": 20,
                "chat": {"id": 100},
                "from": {"id": 1},
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": 1,
                    "invoice_payload": "sess-123",
                    "telegram_payment_charge_id": "charge-dispatch",
                },
            },
        )

        with patch("app.handlers.gif.generate_gif", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = b"gif-bytes"
            await dispatch_update(update)

        doc_calls = [(m, kw) for m, kw in telegram_calls if m == "sendAnimation"]
        assert len(doc_calls) == 1

    @pytest.mark.asyncio
    async def test_unexpected_error_refunds(self, fake_redis, telegram_calls):
        session = _make_session()
        await redis_mod.save_session(session)

        msg = Message(
            message_id=20,
            chat=Chat(id=100),
            from_=TelegramUser(id=1),
            successful_payment=SuccessfulPayment(
                currency="XTR",
                total_amount=1,
                invoice_payload="sess-123",
                telegram_payment_charge_id="charge-unexpected",
            ),
        )

        with patch("app.handlers.gif.generate_gif", new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = RuntimeError("unexpected network error")
            await handle_successful_payment(msg)

        refund_calls = [(m, kw) for m, kw in telegram_calls if m == "refundStarPayment"]
        assert len(refund_calls) == 1

        # Session cleaned up
        assert await redis_mod.get_session("sess-123") is None
