"""Tests for the Lambda webhook handler."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.lambda_webhook import handler


@pytest.fixture(autouse=True)
def _reset_init():
    import app.lambda_webhook as mod
    mod._initialised = True  # skip real init in tests
    yield
    mod._initialised = False


@pytest.fixture
def _mock_sqs():
    mock = MagicMock()
    import app.lambda_webhook as mod
    mod._sqs = mock
    return mock


def _make_event(body, secret=None):
    headers = {}
    if secret is not None:
        headers["x-telegram-bot-api-secret-token"] = secret
    return {
        "headers": headers,
        "body": json.dumps(body),
    }


class TestWebhookSecretValidation:
    def test_rejects_missing_secret(self, fake_redis, telegram_calls):
        event = _make_event({"update_id": 1})
        result = handler(event, None)
        assert result["statusCode"] == 403

    def test_rejects_wrong_secret(self, fake_redis, telegram_calls):
        event = _make_event({"update_id": 1}, secret="wrong")
        result = handler(event, None)
        assert result["statusCode"] == 403

    def test_accepts_correct_secret(self, fake_redis, telegram_calls):
        event = _make_event({"update_id": 1}, secret="test-secret")
        result = handler(event, None)
        assert result["statusCode"] == 200
        assert json.loads(result["body"]) == {"ok": True}


class TestWebhookRouting:
    def test_start_command_dispatched(self, fake_redis, telegram_calls):
        body = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "date": 1700000000,
                "chat": {"id": 42, "type": "private"},
                "text": "/start",
            },
        }
        result = handler(_make_event(body, secret="test-secret"), None)
        assert result["statusCode"] == 200
        methods = [c[0] for c in telegram_calls]
        assert "sendMessage" in methods

    def test_help_command_dispatched(self, fake_redis, telegram_calls):
        body = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "date": 1700000000,
                "chat": {"id": 42, "type": "private"},
                "text": "/help",
            },
        }
        result = handler(_make_event(body, secret="test-secret"), None)
        assert result["statusCode"] == 200
        methods = [c[0] for c in telegram_calls]
        assert "sendMessage" in methods

    def test_successful_payment_enqueued(self, fake_redis, telegram_calls, _mock_sqs):
        body = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "date": 1700000000,
                "chat": {"id": 42, "type": "private"},
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": 10,
                    "invoice_payload": "session-123",
                    "telegram_payment_charge_id": "charge-1",
                    "provider_payment_charge_id": "prov-1",
                },
            },
        }
        with patch.dict("os.environ", {"SQS_QUEUE_URL": "https://sqs.test/queue"}):
            result = handler(_make_event(body, secret="test-secret"), None)

        assert result["statusCode"] == 200
        _mock_sqs.send_message.assert_called_once()
        call_kwargs = _mock_sqs.send_message.call_args[1]
        assert call_kwargs["QueueUrl"] == "https://sqs.test/queue"
        # Verify body is the raw JSON (not re-serialized)
        assert "successful_payment" in call_kwargs["MessageBody"]
        # Should NOT have dispatched to handlers
        assert len(telegram_calls) == 0

    def test_pre_checkout_dispatched(self, fake_redis, telegram_calls):
        body = {
            "update_id": 1,
            "pre_checkout_query": {
                "id": "query-1",
                "from": {"id": 42, "is_bot": False, "first_name": "Test"},
                "currency": "XTR",
                "total_amount": 10,
                "invoice_payload": "session-123",
            },
        }
        result = handler(_make_event(body, secret="test-secret"), None)
        assert result["statusCode"] == 200
        methods = [c[0] for c in telegram_calls]
        assert "answerPreCheckoutQuery" in methods
