"""Required channel/group membership check."""

from __future__ import annotations

import logging
import time

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from django.conf import settings

logger = logging.getLogger(__name__)

MEMBER_STATUSES = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
CHECK_CALLBACK = "check_membership"
# Positive results are cached briefly so every message doesn't cost N API calls.
CACHE_TTL_SECONDS = 300

_verified_until: dict[int, float] = {}


def clear_cache() -> None:
    _verified_until.clear()


async def missing_chats(bot: Bot, user_id: int) -> list[tuple[int | str, str]]:
    """Return the required chats the user has not joined.

    Fails closed: if Telegram can't confirm membership (e.g. the bot is not an
    admin of the channel) the chat is reported as missing and the error logged.
    """
    chats = settings.REQUIRED_CHATS
    if not chats:
        return []
    if _verified_until.get(user_id, 0) > time.monotonic():
        return []

    missing = []
    for chat_id, username in chats:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        except TelegramAPIError as exc:
            logger.error("Cannot check membership of %s in %s: %s", user_id, username, exc)
            missing.append((chat_id, username))
            continue
        is_member = member.status in MEMBER_STATUSES or (
            member.status == ChatMemberStatus.RESTRICTED and getattr(member, "is_member", False)
        )
        if not is_member:
            missing.append((chat_id, username))

    if not missing:
        _verified_until[user_id] = time.monotonic() + CACHE_TTL_SECONDS
    return missing


def membership_keyboard(missing: list[tuple[int | str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"➕ {username} ga a'zo bo'lish", url=f"https://t.me/{username.lstrip('@')}")]
        for _, username in missing
    ]
    rows.append([InlineKeyboardButton(text="🔄 A'zolikni tekshirish", callback_data=CHECK_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def membership_text(missing: list[tuple[int | str, str]]) -> str:
    chats = ", ".join(username for _, username in missing)
    return (
        "⚠️ <b>A'zolik talabi</b>\n\n"
        "❌ Botdan foydalanish uchun quyidagi kanal/guruhlarga a'zo bo'lishingiz kerak:\n"
        f"<code>{chats}</code>\n\n"
        "🔗 Tugmalar orqali a'zo bo'ling va «A'zolikni tekshirish» tugmasini bosing."
    )
