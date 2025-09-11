# bot/middlewares.py
import logging
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import BaseMiddleware
from asgiref.sync import sync_to_async
from core.models import TelegramUser
from django.conf import settings
from bot.bot_instance import bot

logger = logging.getLogger(__name__)


class MembershipMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if await self._should_skip_middleware(event):
            return await handler(event, data)

        user_id = event.from_user.id
        logger.info(f"User {user_id} is checking membership")

        user = await sync_to_async(TelegramUser.objects.filter(telegram_id=user_id).first)()
        if user and user.is_admin:
            logger.info(f"User {user_id} is admin, skipping membership check")
            return await handler(event, data)

        not_member_chats = []
        for chat_id, username in settings.REQUIRED_CHATS:
            try:
                member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                if member.status not in ('member', 'administrator', 'creator'):
                    not_member_chats.append((chat_id, username))
                    logger.debug(f"User {user_id} not a member of {username}")
            except Exception as e:
                logger.error(f"Error checking membership for {username}: {e}")
                not_member_chats.append((chat_id, username))

        if not not_member_chats:
            logger.debug(f"User {user_id} is member of all required chats")
            return await handler(event, data)

        await self._send_membership_required_message(event, not_member_chats)
        return

    async def _should_skip_middleware(self, event) -> bool:
        if (isinstance(event, types.CallbackQuery) and
                event.data == "check_membership"):
            return True

        if isinstance(event, types.Message) and event.text:
            text = event.text.strip()

            if text.startswith(('/', '!')):
                command = text.split('@')[0].lower()

                skip_commands = {
                    '/start', '/help', '/cancel',
                    '/stats', '/broadcast', '/pending_questions',  # Admin komandalari
                    '!start', '!help', '!cancel'
                }

                if any(command.startswith(cmd) for cmd in skip_commands):
                    return True

    async def _send_membership_required_message(self, event, not_member_chats):
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
                text="🔄 Tekshirish",
                callback_data="check_membership"
            )
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=rows)
        chat_links = ', '.join([username for _, username in not_member_chats])

        message_text = (
            f"⚠️ <b>A'zolik talabi</b>\n\n"
            f"❌ Botdan foydalanish uchun quyidagi kanal/guruhlarga a'zo bo'lishingiz kerak:\n"
            f"<code>{chat_links}</code>\n\n"
            f"🔗 Yuqoridagi tugmalar orqali a'zo bo'ling va\n"
            f"«Tekshirish» tugmasini bosing."
        )

        try:
            if isinstance(event, types.Message):
                await event.answer(message_text, reply_markup=markup, parse_mode="HTML")
            elif isinstance(event, types.CallbackQuery):
                await event.message.answer(message_text, reply_markup=markup, parse_mode="HTML")
                await event.answer()
        except Exception as e:
            logger.error(f"Error sending membership message: {e}")