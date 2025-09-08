# run_bot.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from django.conf import settings

from bot.handlers import question, answer, start, common, my_questions, admin_questions

async def main():
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())

    await bot.set_my_commands([
        BotCommand(command="start", description="Botni ishga tushirish"),
        BotCommand(command="help", description="Yordam"),
        BotCommand(command="question", description="Savol yuborish"),
        BotCommand(command="my_questions", description="Mening savollarim"),
        BotCommand(command="pending_questions", description="Javob berilmagan savollar (adminlar uchun)"),  # Add this
        BotCommand(command="cancel", description="Amalni bekor qilish"),
    ])

    question.register(dp)
    answer.register(dp)
    start.register(dp)
    common.register(dp)
    my_questions.register(dp)
    admin_questions.register(dp)


    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
