import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject
from asgiref.sync import sync_to_async
from django.db import close_old_connections

from bot.membership import CHECK_CALLBACK, membership_keyboard, membership_text, missing_chats
from core.services import is_admin

logger = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

# Commands that work without joining the required chats.
PUBLIC_COMMANDS = frozenset({"/start", "/help", "/cancel"})


class DbConnectionMiddleware(BaseMiddleware):
    """Drop stale/broken DB connections around each update.

    Django normally does this on request start/finish; a long-running bot
    process has no requests, so without it a Postgres restart would leave the
    bot with a dead connection forever.
    """

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        await sync_to_async(close_old_connections)()
        try:
            return await handler(event, data)
        finally:
            await sync_to_async(close_old_connections)()


def _is_public(event: TelegramObject) -> bool:
    if isinstance(event, CallbackQuery):
        return event.data == CHECK_CALLBACK
    if isinstance(event, Message) and event.text:
        command = event.text.split(maxsplit=1)[0].split("@", 1)[0].lower()
        return command in PUBLIC_COMMANDS
    return False


class MembershipMiddleware(BaseMiddleware):
    """Block users who haven't joined ``REQUIRED_CHATS`` (admins are exempt)."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = getattr(event, "from_user", None)
        if user is None or _is_public(event) or await is_admin(user.id):
            return await handler(event, data)

        bot: Bot = data["bot"]
        missing = await missing_chats(bot, user.id)
        if not missing:
            return await handler(event, data)

        logger.info("User %s blocked by membership check: %s", user.id, missing)
        text, markup = membership_text(missing), membership_keyboard(missing)
        if isinstance(event, Message):
            await event.answer(text, reply_markup=markup)
        elif isinstance(event, CallbackQuery):
            await event.answer()
            if event.message:
                await event.message.answer(text, reply_markup=markup)
        return None
