"""Admin-only: /stats."""

import logging
from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, OuterRef, Q, Subquery
from django.utils import timezone

from bot.filters import IsAdmin
from core.models import Answer, Question, TelegramUser

logger = logging.getLogger(__name__)

admin_router = Router(name="admin")
admin_router.message.filter(IsAdmin())


async def get_bot_stats() -> dict:
    """Collect statistics in four aggregate queries (no per-question N+1)."""
    now = timezone.now()
    users = await TelegramUser.objects.aaggregate(
        total_users=Count("pk"),
        new_users_30d=Count("pk", filter=Q(created_at__gte=now - timedelta(days=30))),
    )
    questions = await Question.objects.aaggregate(
        total_questions=Count("pk"),
        answered_questions=Count("pk", filter=Q(is_answered=True)),
        in_progress_questions=Count("pk", filter=Q(is_answered=False, in_progress=True)),
        pending_questions=Count("pk", filter=Q(is_answered=False, in_progress=False)),
        questions_24h=Count("pk", filter=Q(created_at__gte=now - timedelta(hours=24))),
        questions_7d=Count("pk", filter=Q(created_at__gte=now - timedelta(days=7))),
    )
    answers = await Answer.objects.aaggregate(
        total_answers=Count("pk"),
        failed_deliveries=Count("pk", filter=Q(delivery_status=Answer.DeliveryStatus.FAILED)),
    )
    first_answer_at = Subquery(
        Answer.objects.filter(question=OuterRef("pk")).order_by("created_at").values("created_at")[:1]
    )
    response = await (
        Question.objects.filter(is_answered=True)
        .annotate(first_answer_at=first_answer_at)
        .filter(first_answer_at__isnull=False)
        .annotate(response_time=ExpressionWrapper(F("first_answer_at") - F("created_at"), output_field=DurationField()))
        .aaggregate(avg_response_time=Avg("response_time"), valid_responses_count=Count("pk"))
    )
    return {**users, **questions, **answers, **response}


def format_duration(value: timedelta | None) -> str:
    if not value:
        return "Noma'lum"
    total = int(value.total_seconds())
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours} soat {minutes} daqiqa"
    if minutes:
        return f"{minutes} daqiqa"
    return f"{seconds} soniya"


def format_stats_text(stats: dict) -> str:
    return (
        "📊 <b>Bot statistikasi</b>\n\n"
        "👥 <b>Foydalanuvchilar:</b>\n"
        f"• Jami: <code>{stats['total_users']}</code>\n"
        f"• Yangi (30 kun): <code>{stats['new_users_30d']}</code>\n\n"
        "📝 <b>Savollar:</b>\n"
        f"• Jami: <code>{stats['total_questions']}</code>\n"
        f"• Oxirgi 24 soat: <code>{stats['questions_24h']}</code>\n"
        f"• Oxirgi 7 kun: <code>{stats['questions_7d']}</code>\n\n"
        "📋 <b>Holati:</b>\n"
        f"• ✅ Javob berilgan: <code>{stats['answered_questions']}</code>\n"
        f"• 🔨 Javob berilmoqda: <code>{stats['in_progress_questions']}</code>\n"
        f"• ⏳ Kutilyapti: <code>{stats['pending_questions']}</code>\n\n"
        "💬 <b>Javoblar:</b>\n"
        f"• Jami: <code>{stats['total_answers']}</code>\n"
        f"• Yetkazilmagan: <code>{stats['failed_deliveries']}</code>\n"
        f"• ⏱️ O'rtacha javob vaqti: {format_duration(stats['avg_response_time'])}\n"
        f"• (Hisoblandi: {stats['valid_responses_count']} ta savoldan)"
    )


@admin_router.message(Command("stats"))
async def stats_handler(message: Message) -> None:
    try:
        stats = await get_bot_stats()
    except Exception:
        logger.exception("Failed to collect stats")
        await message.answer("❌ Statistikani olishda xato yuz berdi")
        return
    await message.answer(format_stats_text(stats))
