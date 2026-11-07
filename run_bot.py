"""Entry point for the Telegram bot worker (long polling + answer outbox)."""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import asyncio  # noqa: E402
import contextlib  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.types import BotCommand  # noqa: E402
from django.conf import settings  # noqa: E402

from bot.delivery import run_outbox  # noqa: E402
from bot.dispatcher import build_dispatcher  # noqa: E402

logger = logging.getLogger("bot")

COMMANDS = [
    BotCommand(command="start", description="Botni ishga tushirish"),
    BotCommand(command="help", description="Yordam"),
    BotCommand(command="question", description="Savol yuborish"),
    BotCommand(command="my_questions", description="Mening savollarim"),
    BotCommand(command="pending_questions", description="Javob berilmagan savollar (adminlar uchun)"),
    BotCommand(command="stats", description="Statistika (adminlar uchun)"),
    BotCommand(command="cancel", description="Amalni bekor qilish"),
]


async def main() -> None:
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    outbox = asyncio.create_task(run_outbox(bot, settings.OUTBOX_POLL_INTERVAL), name="answer-outbox")
    try:
        await bot.set_my_commands(COMMANDS)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        outbox.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await outbox
        await bot.session.close()


if __name__ == "__main__":
    if not settings.BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set. Get one from @BotFather and put it in .env")
        sys.exit(1)
    asyncio.run(main())
