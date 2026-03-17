"""Tests for the Lambda SQS worker handler."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.lambda_worker import handler


@pytest.fixture(autouse=True)
def _reset_init():
    import app.lambda_worker as mod
    mod._initialised = True  # skip real init in tests
    yield
    mod._initialised = False


def _make_sqs_event(body):
    return {
        "Records": [
            {"body": json.dumps(body)},
        ],
    }


class TestWorkerHandler:
    def test_processes_successful_payment(self, fake_redis, telegram_calls):
        body = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "date": 1700000000,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42, "is_bot": False, "first_name": "Test"},
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": 1,
                    "invoice_payload": "session-123",
                    "telegram_payment_charge_id": "charge-1",
                    "provider_payment_charge_id": "prov-1",
                },
            },
        }
        event = _make_sqs_event(body)

        # No session exists → should refund
        handler(event, None)

        methods = [c[0] for c in telegram_calls]
        assert "refundStarPayment" in methods

    def test_exception_propagates_for_sqs_retry(self, fake_redis, telegram_calls):
        """If handle_successful_payment raises, the exception should propagate
        so SQS retries the message."""
        body = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "date": 1700000000,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42, "is_bot": False, "first_name": "Test"},
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": 1,
                    "invoice_payload": "session-123",
                    "telegram_payment_charge_id": "charge-2",
                    "provider_payment_charge_id": "prov-2",
                },
            },
        }
        event = _make_sqs_event(body)

        with patch("app.handlers.handle_successful_payment", new_callable=AsyncMock) as mock_handler:
            mock_handler.side_effect = RuntimeError("generation failed")
            with pytest.raises(RuntimeError, match="generation failed"):
                handler(event, None)
