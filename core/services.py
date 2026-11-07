"""Domain operations shared by the Telegram bot and the Django admin.

All coroutine functions use Django's native async ORM API (``aget``,
``aupdate``...). Multi-statement writes that need a transaction are written as
plain sync functions and wrapped with ``sync_to_async`` because
``transaction.atomic`` is not available in async code.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import ANSWER_TEXT_MAX_LENGTH, QUESTION_TEXT_MAX_LENGTH, Answer, Question, TelegramUser

logger = logging.getLogger(__name__)

# A claim older than this is considered abandoned (admin left mid-answer, bot restarted...).
CLAIM_TTL = timedelta(minutes=30)
MAX_ANSWER_PARTS = 20
CAPTION_MAX_LENGTH = 1024
ANSWER_PART_TYPES = {"text", "photo", "video", "voice", "document"}


@dataclass(frozen=True)
class TelegramProfile:
    """The subset of a Telegram ``User`` we persist."""

    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None

    @classmethod
    def from_aiogram(cls, user: Any) -> TelegramProfile:
        return cls(
            id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=(user.language_code or "")[:10] or None,
        )


# --------------------------------------------------------------------------- users


async def is_admin(telegram_id: int) -> bool:
    """Admins come from the ``TELEGRAM_ADMINS`` env var or the ``is_admin`` flag in the DB."""
    if telegram_id in settings.TELEGRAM_ADMINS:
        return True
    return await TelegramUser.objects.filter(telegram_id=telegram_id, is_admin=True).aexists()


async def upsert_telegram_user(profile: TelegramProfile) -> tuple[TelegramUser, bool]:
    """Create or refresh a Telegram user; promote ids listed in ``TELEGRAM_ADMINS``.

    Users are never demoted here, so admins granted via the web admin keep their role.
    """
    user, created = await TelegramUser.objects.aupdate_or_create(
        telegram_id=profile.id,
        defaults={
            "username": profile.username,
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "language_code": profile.language_code,
        },
    )
    if profile.id in settings.TELEGRAM_ADMINS and not user.is_admin:
        user.is_admin = True
        await user.asave(update_fields=["is_admin"])
    return user, created


async def admin_chat_ids() -> list[int]:
    ids = set(settings.TELEGRAM_ADMINS)
    async for telegram_id in TelegramUser.objects.filter(is_admin=True).values_list("telegram_id", flat=True):
        ids.add(telegram_id)
    return sorted(ids)


# ------------------------------------------------------------------------ questions


def validate_question_text(text: str | None) -> str:
    text = (text or "").strip()
    if not text:
        raise ValidationError("Savol matni bo'sh bo'lmasligi kerak.")
    if len(text) > QUESTION_TEXT_MAX_LENGTH:
        raise ValidationError(f"Savol matni {QUESTION_TEXT_MAX_LENGTH} belgidan oshmasligi kerak.")
    return text


async def create_question(
    user: TelegramUser,
    text: str | None,
    image_file_id: str | None = None,
    document_file_id: str | None = None,
) -> Question:
    return await Question.objects.acreate(
        user=user,
        text=validate_question_text(text),
        image_file_id=image_file_id or None,
        document_file_id=document_file_id or None,
    )


class ClaimResult(enum.Enum):
    CLAIMED = "claimed"
    NOT_FOUND = "not_found"
    ALREADY_ANSWERED = "already_answered"
    LOCKED = "locked"


async def claim_question(question_id: int, admin: TelegramUser) -> ClaimResult:
    """Atomically lock a question for one admin.

    A single conditional ``UPDATE`` avoids the check-then-set race where two
    admins press "Answer" at the same moment.
    """
    now = timezone.now()
    updated = (
        await Question.objects.filter(pk=question_id, is_answered=False)
        .filter(Q(in_progress=False) | Q(claimed_by=admin) | Q(claimed_at__lt=now - CLAIM_TTL))
        .aupdate(in_progress=True, claimed_by=admin, claimed_at=now)
    )
    if updated:
        return ClaimResult.CLAIMED
    question = await Question.objects.filter(pk=question_id).only("is_answered").afirst()
    if question is None:
        return ClaimResult.NOT_FOUND
    if question.is_answered:
        return ClaimResult.ALREADY_ANSWERED
    return ClaimResult.LOCKED


async def release_question(question_id: int) -> None:
    await Question.objects.filter(pk=question_id, is_answered=False).aupdate(
        in_progress=False, claimed_by=None, claimed_at=None
    )


# -------------------------------------------------------------------------- answers


def validate_answer_content(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not content:
        raise ValidationError("Javob bo'sh.")
    if len(content) > MAX_ANSWER_PARTS:
        raise ValidationError(f"Javob {MAX_ANSWER_PARTS} qismdan oshmasligi kerak.")
    for item in content:
        item_type = item.get("type")
        if item_type not in ANSWER_PART_TYPES:
            raise ValidationError(f"Noma'lum javob turi: {item_type!r}")
        if item_type == "text":
            text = (item.get("text") or "").strip()
            if not text:
                raise ValidationError("Matnli qism bo'sh.")
            if len(text) > ANSWER_TEXT_MAX_LENGTH:
                raise ValidationError(f"Matn {ANSWER_TEXT_MAX_LENGTH} belgidan oshmasligi kerak.")
        elif not item.get("file_id"):
            raise ValidationError("Media qismida file_id yo'q.")
        elif len(item.get("caption") or "") > CAPTION_MAX_LENGTH:
            raise ValidationError(f"Izoh {CAPTION_MAX_LENGTH} belgidan oshmasligi kerak.")
    return content


def save_answer(answer: Answer) -> Answer:
    """Persist a new answer and mark its question answered in one transaction.

    The answer starts in ``PENDING`` delivery state; the bot delivers it (right
    away when answered from Telegram, or via the outbox poller when answered from
    the web admin). Saving first means an answer is never lost if Telegram is
    unreachable or the user has blocked the bot.
    """
    validate_answer_content(answer.content)
    with transaction.atomic():
        question = Question.objects.select_for_update().get(pk=answer.question_id)
        answer.delivery_status = Answer.DeliveryStatus.PENDING
        answer.save()
        question.is_answered = True
        question.in_progress = False
        question.claimed_by = None
        question.claimed_at = None
        question.save(update_fields=["is_answered", "in_progress", "claimed_by", "claimed_at"])
    logger.info("Answer %s saved for question %s", answer.pk, question.pk)
    return answer


def create_answer(
    question: Question | int,
    content: list[dict[str, Any]],
    *,
    responder: TelegramUser | None = None,
    staff_user: Any = None,
) -> Answer:
    question_id = question.pk if isinstance(question, Question) else question
    return save_answer(Answer(question_id=question_id, content=content, responder=responder, staff_user=staff_user))


acreate_answer = sync_to_async(create_answer)
