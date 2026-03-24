"""Tests for app/stats.py (S3-backed GIF counter) and GET /stats webhook route."""

import json
import os
import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "operation")


def _make_get_response(count: int, etag: str = '"abc123"'):
    body_mock = MagicMock()
    body_mock.read.return_value = json.dumps({"count": count}).encode()
    return {"Body": body_mock, "ETag": etag}


# ---------------------------------------------------------------------------
# get_gif_count
# ---------------------------------------------------------------------------

class TestGetGifCount:
    def test_returns_zero_when_object_missing(self, monkeypatch):
        monkeypatch.setenv("S3_STATS_BUCKET", "test-bucket")
        s3_mock = MagicMock()
        s3_mock.get_object.side_effect = _client_error("NoSuchKey")

        import app.stats as stats_mod
        monkeypatch.setattr(stats_mod, "_s3", s3_mock)

        assert stats_mod.get_gif_count() == 0

    def test_returns_count_from_s3(self, monkeypatch):
        monkeypatch.setenv("S3_STATS_BUCKET", "test-bucket")
        s3_mock = MagicMock()
        s3_mock.get_object.return_value = _make_get_response(42)

        import app.stats as stats_mod
        monkeypatch.setattr(stats_mod, "_s3", s3_mock)

        assert stats_mod.get_gif_count() == 42

    def test_propagates_unexpected_errors(self, monkeypatch):
        monkeypatch.setenv("S3_STATS_BUCKET", "test-bucket")
        s3_mock = MagicMock()
        s3_mock.get_object.side_effect = _client_error("AccessDenied")

        import app.stats as stats_mod
        monkeypatch.setattr(stats_mod, "_s3", s3_mock)

        with pytest.raises(ClientError):
            stats_mod.get_gif_count()


# ---------------------------------------------------------------------------
# increment_gif_count
# ---------------------------------------------------------------------------

class TestIncrementGifCount:
    def test_increments_existing_count(self, monkeypatch):
        monkeypatch.setenv("S3_STATS_BUCKET", "test-bucket")
        s3_mock = MagicMock()
        s3_mock.get_object.return_value = _make_get_response(9)
        s3_mock.put_object.return_value = {}

        import app.stats as stats_mod
        monkeypatch.setattr(stats_mod, "_s3", s3_mock)

        result = stats_mod.increment_gif_count()
        assert result == 10

        call_kwargs = s3_mock.put_object.call_args.kwargs
        assert call_kwargs["IfMatch"] == '"abc123"'
        assert json.loads(call_kwargs["Body"])["count"] == 10

    def test_first_write_uses_if_none_match(self, monkeypatch):
        monkeypatch.setenv("S3_STATS_BUCKET", "test-bucket")
        s3_mock = MagicMock()
        s3_mock.get_object.side_effect = _client_error("NoSuchKey")
        s3_mock.put_object.return_value = {}

        import app.stats as stats_mod
        monkeypatch.setattr(stats_mod, "_s3", s3_mock)

        result = stats_mod.increment_gif_count()
        assert result == 1

        call_kwargs = s3_mock.put_object.call_args.kwargs
        assert call_kwargs["IfNoneMatch"] == "*"
        assert json.loads(call_kwargs["Body"])["count"] == 1

    def test_retries_on_precondition_failed(self, monkeypatch):
        monkeypatch.setenv("S3_STATS_BUCKET", "test-bucket")
        s3_mock = MagicMock()

        # First GET returns count=5, second GET returns count=6 (after conflict)
        s3_mock.get_object.side_effect = [
            _make_get_response(5, '"etag1"'),
            _make_get_response(6, '"etag2"'),
        ]
        # First PUT fails with 412, second succeeds
        s3_mock.put_object.side_effect = [
            _client_error("PreconditionFailed"),
            {},
        ]

        import app.stats as stats_mod
        monkeypatch.setattr(stats_mod, "_s3", s3_mock)

        result = stats_mod.increment_gif_count()
        assert result == 7
        assert s3_mock.get_object.call_count == 2
        assert s3_mock.put_object.call_count == 2

    def test_raises_after_max_retries(self, monkeypatch):
        monkeypatch.setenv("S3_STATS_BUCKET", "test-bucket")
        s3_mock = MagicMock()
        s3_mock.get_object.return_value = _make_get_response(1)
        s3_mock.put_object.side_effect = _client_error("PreconditionFailed")

        import app.stats as stats_mod
        monkeypatch.setattr(stats_mod, "_s3", s3_mock)

        with pytest.raises(RuntimeError, match="retries"):
            stats_mod.increment_gif_count()


# ---------------------------------------------------------------------------
# GET /stats webhook handler
# ---------------------------------------------------------------------------

class TestWebhookStatsRoute:
    def _make_event(self, method="GET", path="/stats"):
        return {
            "requestContext": {"http": {"method": method, "path": path}},
            "headers": {},
            "body": "{}",
        }

    def test_returns_count_with_cors_headers(self, monkeypatch):
        monkeypatch.setenv("S3_STATS_BUCKET", "test-bucket")

        import app.stats as stats_mod
        import app.lambda_webhook as wh

        # Reset init state so _ensure_init doesn't try to connect to real Redis
        wh._initialised = False
        monkeypatch.setattr(stats_mod, "_s3", MagicMock(
            get_object=MagicMock(return_value=_make_get_response(77))
        ))

        with patch("app.lambda_webhook._ensure_init"):
            resp = wh.handler(self._make_event(), None)

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["count"] == 77
        assert resp["headers"]["Access-Control-Allow-Origin"] == "https://anygifbot.com"
        assert "max-age=60" in resp["headers"]["Cache-Control"]

    def test_does_not_require_telegram_secret(self, monkeypatch):
        monkeypatch.setenv("S3_STATS_BUCKET", "test-bucket")

        import app.stats as stats_mod
        import app.lambda_webhook as wh

        monkeypatch.setattr(stats_mod, "_s3", MagicMock(
            get_object=MagicMock(return_value=_make_get_response(0))
        ))

        # No x-telegram-bot-api-secret-token header present
        with patch("app.lambda_webhook._ensure_init"):
            resp = wh.handler(self._make_event(), None)

        assert resp["statusCode"] == 200

    def test_non_stats_path_still_requires_telegram_auth(self, monkeypatch):
        import app.lambda_webhook as wh

        event = self._make_event(method="POST", path="/webhook")
        event["body"] = json.dumps({"update_id": 1})

        with patch("app.lambda_webhook._ensure_init"):
            with patch("app.lambda_webhook.config.get_webhook_secret", return_value="secret"):
                resp = wh.handler(event, None)

        assert resp["statusCode"] == 403
