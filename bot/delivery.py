"""Delivery of saved answers to students (a tiny transactional outbox).

Every answer is first stored with ``delivery_status=pending``. This module
claims pending answers one by one, sends them through the Bot API and records
the outcome:

* success                         -> ``delivered``
* user blocked the bot / bad data -> ``failed`` (permanent, error stored)
* network / flood / server error  -> back to ``pending`` until ``MAX_ATTEMPTS``

Answers written in the Django admin are picked up by :func:`run_outbox`, which
runs inside the bot process, so the web process never needs the bot token.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramRetryAfter,
)
from asgiref.sync import sync_to_async
from django.db import close_old_connections
from django.db.models import F
from django.utils import timezone

from bot.utils.telegram import send_content
from core.models import Answer

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
BATCH_SIZE = 20
ANSWER_HEADER = "📬 Sizning savolingizga javob keldi:"

# Retrying these can never succeed (user blocked the bot, chat/file not found...).
PERMANENT_ERRORS = (TelegramForbiddenError, TelegramBadRequest, TelegramNotFound)

Status = Answer.DeliveryStatus


async def _mark(answer_id: int, **fields) -> None:
    await Answer.objects.filter(pk=answer_id).aupdate(**fields)


async def deliver_answer(bot: Bot, answer_id: int) -> bool:
    """Try to deliver one answer. Returns True when it was delivered."""
    # Atomic claim: only one coroutine/process can move pending -> sending.
    claimed = await Answer.objects.filter(pk=answer_id, delivery_status=Status.PENDING).aupdate(
        delivery_status=Status.SENDING, delivery_attempts=F("delivery_attempts") + 1
    )
    if not claimed:
        return False

    answer = await Answer.objects.select_related("question__user").aget(pk=answer_id)
    chat_id = answer.question.user.telegram_id
    try:
        await bot.send_message(chat_id, ANSWER_HEADER)
        await send_content(bot, chat_id, answer.content)
    except PERMANENT_ERRORS as exc:
        logger.warning("Answer %s permanently failed for chat %s: %s", answer_id, chat_id, exc)
        await _mark(answer_id, delivery_status=Status.FAILED, delivery_error=str(exc)[:500])
        return False
    except TelegramAPIError as exc:  # network, flood control, 5xx: retry later
        exhausted = answer.delivery_attempts >= MAX_ATTEMPTS
        logger.warning(
            "Answer %s transient failure (attempt %s/%s): %s",
            answer_id,
            answer.delivery_attempts,
            MAX_ATTEMPTS,
            exc,
        )
        await _mark(
            answer_id,
            delivery_status=Status.FAILED if exhausted else Status.PENDING,
            delivery_error=str(exc)[:500],
        )
        if isinstance(exc, TelegramRetryAfter):
            await asyncio.sleep(min(exc.retry_after, 60))
        return False
    except Exception as exc:
        # Unknown error: don't leave the answer stuck in "sending".
        logger.exception("Unexpected error delivering answer %s", answer_id)
        await _mark(answer_id, delivery_status=Status.PENDING, delivery_error=str(exc)[:500])
        raise

    await _mark(answer_id, delivery_status=Status.DELIVERED, delivered_at=timezone.now(), delivery_error="")
    logger.info("Answer %s delivered to chat %s", answer_id, chat_id)
    return True


async def deliver_pending_answers(bot: Bot, limit: int = BATCH_SIZE) -> int:
    """Deliver up to ``limit`` pending answers, oldest first. Returns delivered count."""
    ids = [
        pk
        async for pk in Answer.objects.filter(delivery_status=Status.PENDING)
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    ]
    delivered = 0
    for answer_id in ids:
        if await deliver_answer(bot, answer_id):
            delivered += 1
    return delivered


async def reset_stuck_answers() -> int:
    """Answers left in ``sending`` by a crashed worker go back to ``pending``."""
    return await Answer.objects.filter(delivery_status=Status.SENDING).aupdate(delivery_status=Status.PENDING)


async def run_outbox(bot: Bot, interval: float) -> None:
    """Background loop started by ``run_bot.py``."""
    reset = await reset_stuck_answers()
    if reset:
        logger.info("Re-queued %s answers stuck in 'sending'", reset)
    logger.info("Answer outbox started (interval=%ss)", interval)
    while True:
        try:
            await sync_to_async(close_old_connections)()
            await deliver_pending_answers(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Outbox iteration failed")
        await asyncio.sleep(interval)
