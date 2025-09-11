from aiogram import Router, types, F
from aiogram.filters import Command
from asgiref.sync import sync_to_async
from core.models import TelegramUser, Question, Answer
from django.db.models import Count, Q, Avg, ExpressionWrapper, DurationField
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

admin_router = Router()


@sync_to_async
def check_is_admin(user_id: int) -> bool:
    return TelegramUser.objects.filter(telegram_id=user_id, is_admin=True).exists()


async def is_admin(user_id: int) -> bool:
    return await check_is_admin(user_id)


@admin_router.message(Command("stats"))
async def stats_handler(message: types.Message):

    if not await is_admin(message.from_user.id):
        await message.answer("❌ Bu buyruq faqat adminlar uchun!")
        return

    try:
        stats = await get_bot_stats()

        stats_text = format_stats_text(stats)

        await message.answer(stats_text, parse_mode="HTML")
        logger.info(f"Admin {message.from_user.id} requested stats")

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        await message.answer("❌ Statistikani olishda xato yuz berdi")


@sync_to_async
def get_basic_stats():
    total_users = TelegramUser.objects.count()

    active_users = TelegramUser.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=30)
    ).count()

    total_questions = Question.objects.count()

    answered_questions = Question.objects.filter(is_answered=True).count()
    pending_questions = Question.objects.filter(is_answered=False, in_progress=False).count()
    in_progress_questions = Question.objects.filter(in_progress=True, is_answered=False).count()

    questions_24h = Question.objects.filter(
        created_at__gte=timezone.now() - timedelta(hours=24)
    ).count()

    questions_7d = Question.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7)
    ).count()

    total_answers = Answer.objects.count()

    return {
        'total_users': total_users,
        'active_users': active_users,
        'total_questions': total_questions,
        'answered_questions': answered_questions,
        'pending_questions': pending_questions,
        'in_progress_questions': in_progress_questions,
        'questions_24h': questions_24h,
        'questions_7d': questions_7d,
        'total_answers': total_answers,
    }


@sync_to_async
def get_response_time_stats():
    answered_questions_with_answers = list(Question.objects.filter(
        is_answered=True,
        answers__isnull=False
    ).prefetch_related('answers'))

    total_response_time = timedelta(0)
    valid_responses = 0

    for question in answered_questions_with_answers:
        if question.answers.exists():
            first_answer = question.answers.earliest('created_at')
            response_time = first_answer.created_at - question.created_at
            if response_time.total_seconds() > 0:
                total_response_time += response_time
                valid_responses += 1

    avg_response_time = total_response_time / valid_responses if valid_responses > 0 else timedelta(0)

    return {
        'avg_response_time': avg_response_time,
        'valid_responses_count': valid_responses
    }


async def get_bot_stats():
    basic_stats = await get_basic_stats()

    response_time_stats = await get_response_time_stats()

    stats = {**basic_stats, **response_time_stats}

    return stats


def format_stats_text(stats: dict) -> str:
    avg_time = stats['avg_response_time']
    if isinstance(avg_time, timedelta):
        total_seconds = avg_time.total_seconds()
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if hours > 0:
            avg_time_str = f"{int(hours)} soat {int(minutes)} daqiqa"
        elif minutes > 0:
            avg_time_str = f"{int(minutes)} daqiqa"
        else:
            seconds = total_seconds
            avg_time_str = f"{int(seconds)} soniya"
    else:
        avg_time_str = "Noma'lum"

    text = (
        "📊 <b>Bot Statistikasi</b>\n\n"

        "👥 <b>Foydalanuvchilar:</b>\n"
        f"• Jami: <code>{stats['total_users']}</code>\n"
        f"• Faol (30 kun): <code>{stats['active_users']}</code>\n\n"

        "📝 <b>Savollar:</b>\n"
        f"• Jami: <code>{stats['total_questions']}</code>\n"
        f"• Oxirgi 24 soat: <code>{stats['questions_24h']}</code>\n"
        f"• Oxirgi 7 kun: <code>{stats['questions_7d']}</code>\n\n"

        "📋 <b>Savollar holati:</b>\n"
        f"• ✅ Javob berilgan: <code>{stats['answered_questions']}</code>\n"
        f"• 🔨 Javob berilmoqda: <code>{stats['in_progress_questions']}</code>\n"
        f"• ⏳ Kutilyapti: <code>{stats['pending_questions']}</code>\n\n"

        "💬 <b>Javoblar:</b>\n"
        f"• Jami javoblar: <code>{stats['total_answers']}</code>\n"
        f"• ⏱️ O'rtacha javob vaqti: {avg_time_str}\n"
        f"• (Hisoblandi: {stats['valid_responses_count']} ta savoldan)\n\n"

        "🔄 <i>Statistika real vaqtda yangilanadi</i>"
    )

    return text


@admin_router.message(Command("broadcast"))
async def broadcast_handler(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Bu buyruq faqat adminlar uchun!")
        return

    await message.answer("📢 Broadcast funksiyasi tez orada qo'shiladi!")


def register(dp):
    dp.include_async_router(admin_router)