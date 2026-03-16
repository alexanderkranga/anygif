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
        body = {"charge_id": "charge-1", "session_id": "session-123"}
        event = _make_sqs_event(body)

        with patch("app.handlers.handle_successful_payment", new_callable=AsyncMock) as mock_handler:
            handler(event, None)
            mock_handler.assert_called_once_with("charge-1", "session-123")

    def test_exception_propagates_for_sqs_retry(self, fake_redis, telegram_calls):
        """If handle_successful_payment raises, the exception should propagate
        so SQS retries the message."""
        body = {"charge_id": "charge-2", "session_id": "session-123"}
        event = _make_sqs_event(body)

        with patch("app.handlers.handle_successful_payment", new_callable=AsyncMock) as mock_handler:
            mock_handler.side_effect = RuntimeError("generation failed")
            with pytest.raises(RuntimeError, match="generation failed"):
                handler(event, None)
