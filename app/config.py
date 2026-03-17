"""Configuration — all env vars read lazily for testability."""

import os


def get_bot_token() -> str:
    return os.environ["TELEGRAM_BOT_TOKEN"]


def get_webhook_secret() -> str:
    return os.environ["TELEGRAM_WEBHOOK_SECRET"]


def get_redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379")


def get_generation_price() -> int:
    return int(os.getenv("GENERATION_PRICE_STARS", "10"))


def get_session_ttl() -> int:
    return int(os.getenv("SESSION_TTL_SECONDS", "600"))


def get_proxy_url() -> str | None:
    """Decodo residential proxy URL, e.g. http://user:pass@gate.decodo.com:7000"""
    return os.getenv("DECODO_PROXY_URL")
