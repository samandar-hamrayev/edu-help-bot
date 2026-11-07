"""Best-effort notifications to admins."""

import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.telegram import CAPTION_MAX_LENGTH, MESSAGE_MAX_LENGTH, display_name, escape, safe_call, truncate
from core.models import Question, TelegramUser
from core.services import admin_chat_ids

logger = logging.getLogger(__name__)


def answer_keyboard(question_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✍️ Javob berish", callback_data=f"answer_q_{question_id}")]]
    )


def new_question_text(question: Question, user: TelegramUser, limit: int) -> str:
    header = f"🆕 <b>Yangi savol</b> (ID: {question.pk})\n"
    footer = f"\n\n👤 {escape(display_name(user))} (ID: <code>{user.telegram_id}</code>)"
    # Truncate the raw text *before* escaping so we never cut an HTML entity in half.
    budget = max(limit - len(header) - len(footer) - 50, 50)
    return header + escape(truncate(question.text or "", budget)) + footer


async def notify_admins_new_question(bot: Bot, question: Question, user: TelegramUser) -> int:
    """Send the question to every admin; returns how many were reached."""
    markup = answer_keyboard(question.pk)
    sent = 0
    for chat_id in await admin_chat_ids():
        if question.image_file_id:
            call = bot.send_photo(
                chat_id,
                question.image_file_id,
                caption=new_question_text(question, user, CAPTION_MAX_LENGTH),
                reply_markup=markup,
            )
        elif question.document_file_id:
            call = bot.send_document(
                chat_id,
                question.document_file_id,
                caption=new_question_text(question, user, CAPTION_MAX_LENGTH),
                reply_markup=markup,
            )
        else:
            call = bot.send_message(chat_id, new_question_text(question, user, MESSAGE_MAX_LENGTH), reply_markup=markup)
        if await safe_call(call, chat_id=chat_id) is not None:
            sent += 1
    logger.info("Question %s announced to %s admin(s)", question.pk, sent)
    return sent


async def notify_admins_new_user(bot: Bot, user: TelegramUser) -> None:
    text = (
        f"🔔 Yangi foydalanuvchi: <a href='tg://user?id={user.telegram_id}'>{escape(display_name(user))}</a>\n"
        f"ID: <code>{user.telegram_id}</code> | Til: {escape(user.language_code or '-')}"
    )
    for chat_id in await admin_chat_ids():
        if chat_id != user.telegram_id:
            await safe_call(bot.send_message(chat_id, text), chat_id=chat_id)
