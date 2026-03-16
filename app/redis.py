"""Redis helpers for sessions and dedup."""

from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis

from app.config import get_session_ttl
from app.models import Session

# Singleton connection — set during app lifespan
_redis: Optional[aioredis.Redis] = None


def set_redis(r: aioredis.Redis) -> None:
    global _redis
    _redis = r


def get_redis() -> aioredis.Redis:
    assert _redis is not None, "Redis not initialised"
    return _redis


# ── Sessions ────────────────────────────────────────────────────────

async def save_session(session: Session) -> None:
    r = get_redis()
    key = f"session:{session.session_id}"
    await r.set(key, session.model_dump_json(), ex=get_session_ttl())


async def get_session(session_id: str) -> Optional[Session]:
    r = get_redis()
    raw = await r.get(f"session:{session_id}")
    if raw is None:
        return None
    return Session.model_validate_json(raw)


async def delete_session(session_id: str) -> None:
    r = get_redis()
    await r.delete(f"session:{session_id}")


# ── Dedup ───────────────────────────────────────────────────────────

async def check_and_set_dedup(charge_id: str) -> bool:
    """Returns True if this is a NEW charge (not seen before)."""
    r = get_redis()
    was_set = await r.set(f"dedup:{charge_id}", "1", nx=True, ex=86400)
    return was_set is not None  # True if key was newly set


# ── Refund fallback ─────────────────────────────────────────────────
_REFUND_FALLBACK_TTL = 3600  # 1 hour

async def save_refund_fallback(session_id: str, user_id: int) -> None:
    r = get_redis()
    await r.set(f"refund:{session_id}", str(user_id), ex=_REFUND_FALLBACK_TTL)

async def get_and_delete_refund_fallback(session_id: str) -> Optional[int]:
    r = get_redis()
    raw = await r.getdel(f"refund:{session_id}")
    if raw is None:
        return None
    return int(raw)
