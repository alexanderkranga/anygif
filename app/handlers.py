"""Telegram update dispatch and handler logic."""

from __future__ import annotations

import logging
import re
import uuid
import time
from typing import Optional

from app import config, redis as redis_mod, telegram as tg, gif
from app.models import Update, Message, PreCheckoutQuery, Session

logger = logging.getLogger(__name__)

START_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
USAGE_EXAMPLE = "Usage: `/gif <URL> <start_time> <duration>`\nExample: `/gif https://youtube.com/watch?v=abc123 1:30 5`"


async def dispatch_update(update: Update) -> None:
    """Route an incoming Telegram update to the appropriate handler."""
    if update.pre_checkout_query is not None:
        await handle_pre_checkout(update.pre_checkout_query)
        return

    if update.message is not None:
        msg = update.message

        # Successful payment
        if msg.successful_payment is not None:
            await handle_successful_payment(
                msg.successful_payment.telegram_payment_charge_id,
                msg.successful_payment.invoice_payload,
            )
            return

        text = msg.text or ""

        # Commands
        if text.startswith("/start"):
            await handle_start(msg)
            return
        if text.startswith("/help"):
            await handle_help(msg)
            return
        if text.startswith("/gif"):
            await handle_gif_command(msg)
            return

    # Everything else — ignore silently


async def handle_start(msg: Message) -> None:
    price = config.get_generation_price()
    text = (
        f"Welcome to AnyGif!\n\n"
        f"I create GIFs from any video on the internet! "
        f"Just give me a URL, a start time, and a duration (max 10 seconds).\n\n"
        f"Works with YouTube, Vimeo, Twitter, TikTok, Reddit, Instagram, "
        f"and 1000+ other sites.\n\n"
        f"Price: {price} Stars per generation.\n\n"
        f"How to use:\n"
        f"  /gif <URL> <start_time> <duration_seconds>\n\n"
        f"Example:\n"
        f"  /gif https://www.youtube.com/watch?v=dQw4w9WgXcQ 0:01 5\n\n"
        f"Refund policy: Guaranteed automatic refund on any generation failure."
    )
    await tg.send_message(msg.chat.id, text)


async def handle_help(msg: Message) -> None:
    text = (
        "Usage:\n\n"
        "/gif <URL> <start_time> <duration_seconds>\n\n"
        "Parameters:\n"
        "• URL — any video URL\n"
        "• start_time — start timestamp in m:ss or mm:ss format\n"
        "• duration_seconds — GIF duration (1-10 seconds)\n\n"
        "Example:\n"
        "  /gif https://www.youtube.com/watch?v=dQw4w9WgXcQ 0:01 5\n\n"
        "Refund policy: Automatic refund on any generation failure."
    )
    await tg.send_message(msg.chat.id, text)


async def handle_gif_command(msg: Message) -> None:
    """Handle /gif command — parse params, validate, send invoice."""
    text = msg.text or ""
    parts = text.split()

    # Expect: /gif <URL> <start_time> <duration>
    if len(parts) != 4:
        await tg.send_message(
            msg.chat.id,
            f"Please provide all 3 parameters.\n{USAGE_EXAMPLE}",
            reply_to_message_id=msg.message_id,
            parse_mode="Markdown",
        )
        return

    _, video_url, start_time, duration_str = parts

    # Validate start_time
    if not START_TIME_RE.match(start_time):
        await tg.send_message(
            msg.chat.id,
            f"Invalid start time `{start_time}`. Use m:ss or mm:ss format.\n{USAGE_EXAMPLE}",
            reply_to_message_id=msg.message_id,
            parse_mode="Markdown",
        )
        return

    # Validate duration
    try:
        duration = int(duration_str)
    except ValueError:
        await tg.send_message(
            msg.chat.id,
            f"Duration must be an integer.\n{USAGE_EXAMPLE}",
            reply_to_message_id=msg.message_id,
            parse_mode="Markdown",
        )
        return

    if duration < 1 or duration > 10:
        await tg.send_message(
            msg.chat.id,
            f"Duration must be between 1 and 10 seconds.\n{USAGE_EXAMPLE}",
            reply_to_message_id=msg.message_id,
            parse_mode="Markdown",
        )
        return

    # Create session
    session_id = str(uuid.uuid4())
    user_id = msg.from_.id if msg.from_ else 0
    session = Session(
        session_id=session_id,
        user_id=user_id,
        chat_id=msg.chat.id,
        original_message_id=msg.message_id,
        video_url=video_url,
        start_time=start_time,
        duration=duration,
        expires_at=time.time() + config.get_session_ttl(),
    )
    await redis_mod.save_session(session)

    # Send invoice
    price = config.get_generation_price()
    invoice_resp = await tg.send_invoice(
        chat_id=msg.chat.id,
        title="GIF Generation",
        description=f"GIF @ {start_time} ({duration}s)",
        payload=session_id,
        currency="XTR",
        prices=[{"label": "1 GIF", "amount": price}],
        reply_to_message_id=msg.message_id,
    )
    if invoice_resp.get("ok") and invoice_resp.get("result"):
        session.invoice_message_id = invoice_resp["result"]["message_id"]
        await redis_mod.save_session(session)


async def handle_pre_checkout(query: PreCheckoutQuery) -> None:
    """Validate session before Telegram finalises payment."""
    session_id = query.invoice_payload
    session = await redis_mod.get_session(session_id)

    if session is None:
        await tg.answer_pre_checkout_query(
            query.id, ok=False, error_message="Session expired, please send /gif again."
        )
        return

    await tg.answer_pre_checkout_query(query.id, ok=True)


async def handle_successful_payment(charge_id: str, session_id: str) -> None:
    """Process confirmed payment — generate GIF or refund."""
    # Dedup check
    is_new = await redis_mod.check_and_set_dedup(charge_id)
    if not is_new:
        return  # duplicate webhook

    session = await redis_mod.get_session(session_id)

    if session is None:
        user_id = await redis_mod.get_and_delete_refund_fallback(session_id)
        if user_id is None:
            logger.error("Missing session and refund fallback for session %s", session_id)
            return
        await tg.refund_star_payment(user_id, charge_id)
        return

    # Delete the invoice message so the user cannot pay again accidentally
    if session.invoice_message_id is not None:
        await tg.delete_message(session.chat_id, session.invoice_message_id)

    # Send "Generating..." message
    gen_resp = await tg.send_message(
        session.chat_id,
        "Generating your GIF...",
        reply_to_message_id=session.original_message_id,
    )
    processing_message_id = None
    if gen_resp.get("ok") and gen_resp.get("result"):
        processing_message_id = gen_resp["result"]["message_id"]

    try:
        # Generate GIF
        gif_bytes = await gif.generate_gif(
            session.video_url, session.start_time, session.duration
        )

        # Delete "Generating..." message
        if processing_message_id:
            await tg.delete_message(session.chat_id, processing_message_id)

        # Send as animation (autoplays + loops in Telegram, like a GIF)
        await tg.send_animation(
            session.chat_id,
            gif_bytes,
            filename="anygif.mp4",
            reply_to_message_id=session.original_message_id,
        )

    except Exception as e:
        logger.error("GIF generation failed for session %s: %s", session_id, type(e).__name__)
        if processing_message_id:
            await tg.delete_message(session.chat_id, processing_message_id)
        await tg.refund_star_payment(session.user_id, charge_id)
        await tg.send_message(
            session.chat_id,
            "GIF generation failed. Your Stars have been refunded. Please, try again later.",
            reply_to_message_id=session.original_message_id,
        )

    finally:
        await redis_mod.delete_session(session_id)
