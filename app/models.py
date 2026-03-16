"""Pydantic models for Telegram updates and internal state."""

from __future__ import annotations

from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


# ── Telegram types (only fields we use) ─────────────────────────────

class TelegramUser(BaseModel):
    id: int
    first_name: Optional[str] = None


class Document(BaseModel):
    file_id: str
    file_name: Optional[str] = None
    mime_type: Optional[str] = None


class SuccessfulPayment(BaseModel):
    currency: str
    total_amount: int
    invoice_payload: str
    telegram_payment_charge_id: str


class Chat(BaseModel):
    id: int
    type: Optional[str] = None


class PreCheckoutQuery(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_: TelegramUser = Field(alias="from")
    currency: str
    total_amount: int
    invoice_payload: str


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: int
    from_: Optional[TelegramUser] = Field(default=None, alias="from")
    chat: Chat
    text: Optional[str] = None
    successful_payment: Optional[SuccessfulPayment] = None


class Update(BaseModel):
    update_id: int
    message: Optional[Message] = None
    pre_checkout_query: Optional[PreCheckoutQuery] = None


# ── Internal models ─────────────────────────────────────────────────

class Session(BaseModel):
    session_id: str
    user_id: int
    chat_id: int
    original_message_id: int
    video_url: str
    start_time: str
    duration: int
    expires_at: float
    invoice_message_id: Optional[int] = None
