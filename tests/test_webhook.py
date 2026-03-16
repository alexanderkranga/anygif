"""Tests for the webhook endpoint — secret validation, request handling."""

import pytest


class TestWebhook:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_webhook_rejects_missing_secret(self, client):
        resp = client.post("/webhook", json={"update_id": 1})
        assert resp.status_code == 403

    def test_webhook_rejects_wrong_secret(self, client):
        resp = client.post(
            "/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        )
        assert resp.status_code == 403

    def test_webhook_accepts_correct_secret(self, client):
        resp = client.post(
            "/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
