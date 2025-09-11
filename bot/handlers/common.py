# bot/handlers/common.py
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from core.models import Question, TelegramUser
from asgiref.sync import sync_to_async
from bot.handlers.answer import AnswerStates
from bot.handlers.question import QuestionStates
from django.conf import settings
from bot.bot_instance import bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

logger = logging.getLogger(__name__)

common_router = Router()


@common_router.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()

    if not current_state:
        await message.answer("ℹ️ Hozirda hech qanday jarayon faol emas. /start bilan boshlang.")
        return

    if current_state in AnswerStates.__states__:
        data = await state.get_data()
        question_id = data.get("question_id")
        if question_id:
            try:
                question = await sync_to_async(Question.objects.get)(id=question_id)
                question.in_progress = False
                await sync_to_async(question.save)()
                logger.info(f"Question {question_id} progress reset by cancel")
            except Question.DoesNotExist:
                logger.warning(f"Question {question_id} not found for cancel")
            except Exception as e:
                logger.error(f"Error resetting question progress: {e}")

        await message.answer("✋ Javob berish jarayoni bekor qilindi.")
        logger.info(f"Answer process cancelled by user {message.from_user.id}")

    elif current_state in QuestionStates.__states__:
        await message.answer("❌ Savol yuborish jarayoni bekor qilindi.")
        logger.info(f"Question process cancelled by user {message.from_user.id}")

    else:
        await message.answer("ℹ️ Joriy jarayon bekor qilindi.")
        logger.info(f"Unknown process cancelled by user {message.from_user.id}")

    await state.clear()


@common_router.callback_query(F.data == "check_membership")
async def check_membership_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    logger.info(f"Membership check requested by user {user_id}")

    try:
        user = await sync_to_async(TelegramUser.objects.filter(telegram_id=user_id).first)()
        if user and user.is_admin:
            await call.message.edit_text(
                "✅ Siz adminsiz, a'zolik talab qilinmaydi. Botning barcha funksiyalaridan foydalanishingiz mumkin.",
                reply_markup=None
            )
            await call.answer("Siz admin ekansiz")
            logger.info(f"User {user_id} is admin, membership not required")
            return
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id}: {e}")

    not_member_chats = []
    for chat_id, username in settings.REQUIRED_CHATS:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status not in ('member', 'administrator', 'creator'):
                not_member_chats.append((chat_id, username))
                logger.debug(f"User {user_id} not member of {username}")
        except Exception as e:
            logger.error(f"Error checking membership for {username}: {e}")
            not_member_chats.append((chat_id, username))

    if not not_member_chats:
        await call.message.edit_text(
            "✅ Endi barcha kanal/guruhlarga a'zo bo'ldingiz!\n\n"
            "🎉 Botdan to'liq foydalanishingiz mumkin:\n"
            "• /question - Savol berish\n"
            "• /my_questions - Mening savollarim\n"
            "• /help - Yordam olish",
            reply_markup=None
        )
        await call.answer("A'zolik tekshirildi - ✅")
        logger.info(f"User {user_id} is now member of all required chats")

    else:
        rows = []
        for _, username in not_member_chats:
            rows.append([
                InlineKeyboardButton(
                    text=f"➕ {username} ga a'zo bo'lish",
                    url=f"https://t.me/{username[1:]}"
                )
            ])

        rows.append([
            InlineKeyboardButton(
                text="🔄 A'zolikni tekshirish",
                callback_data="check_membership"
            )
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=rows)
        chat_links = ', '.join([username for _, username in not_member_chats])

        await call.message.edit_text(
            f"⚠️ <b>A'zolik tekshiruvi</b>\n\n"
            f"❌ Hali quyidagi kanal/guruhlarga a'zo bo'lmagansiz:\n"
            f"<code>{chat_links}</code>\n\n"
            f"🔗 Yuqoridagi tugmalar orqali a'zo bo'ling va\n"
            f"«A'zolikni tekshirish» tugmasini bosing.",
            reply_markup=markup,
            parse_mode="HTML"
        )
        await call.answer("A'zolik tekshirildi - Hammasiga azo bo'lishingiz kerak", show_alert=True)
        logger.info(f"User {user_id} still not member of: {chat_links}")


def register(dp):
    dp.include_router(common_router)
    logger.info("Common router registered successfully")