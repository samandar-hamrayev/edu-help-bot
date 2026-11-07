"""Small helpers for talking to the Telegram API safely."""

from __future__ import annotations

import html
import logging
from collections.abc import Awaitable, Iterable
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

logger = logging.getLogger(__name__)

MESSAGE_MAX_LENGTH = 4096
CAPTION_MAX_LENGTH = 1024


def escape(text: Any) -> str:
    """Escape user-provided text for messages sent with ``parse_mode=HTML``."""
    return html.escape(str(text or ""), quote=False)


def truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def display_name(user: Any) -> str:
    return user.first_name or user.username or str(user.telegram_id)


async def safe_call[T](awaitable: Awaitable[T], *, chat_id: int | str) -> T | None:
    """Await a Bot API call, logging (not raising) Telegram errors.

    Used for best-effort notifications where one failure (e.g. an admin who
    blocked the bot) must not abort the whole handler.
    """
    try:
        return await awaitable
    except TelegramForbiddenError:
        logger.warning("Chat %s has blocked the bot or is unreachable", chat_id)
    except TelegramAPIError as exc:
        logger.warning("Telegram API error for chat %s: %s", chat_id, exc)
    return None


async def send_content(bot: Bot, chat_id: int, items: Iterable[dict[str, Any]]) -> None:
    """Send stored answer parts. Raises Telegram errors to the caller.

    Parts are sent as plain text (``parse_mode=None``) so arbitrary characters
    like ``<`` typed by an admin can never break HTML parsing.
    """
    for item in items:
        item_type = item.get("type")
        caption = item.get("caption") or None
        if item_type == "text":
            await bot.send_message(chat_id, item["text"], parse_mode=None)
        elif item_type == "photo":
            await bot.send_photo(chat_id, item["file_id"], caption=caption, parse_mode=None)
        elif item_type == "video":
            await bot.send_video(chat_id, item["file_id"], caption=caption, parse_mode=None)
        elif item_type == "voice":
            await bot.send_voice(chat_id, item["file_id"])
        elif item_type == "document":
            await bot.send_document(chat_id, item["file_id"], caption=caption, parse_mode=None)
        else:
            logger.warning("Skipping unknown content type %r", item_type)
