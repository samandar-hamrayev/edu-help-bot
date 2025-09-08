from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from core.models import TelegramUser
from django.conf import settings
from ..utils.notify_admin import notify_admin_about_new_user
from asgiref.sync import sync_to_async

start_router = Router()

@start_router.message(Command("start"))
async def start_handler(message: Message):
    telegram_id = message.from_user.id

    user, created = await sync_to_async(TelegramUser.objects.get_or_create)(
        telegram_id=telegram_id,
        defaults={
            'username': message.from_user.username,
            'first_name': message.from_user.first_name,
            'last_name': message.from_user.last_name,
            'language_code': message.from_user.language_code,
            'is_admin': str(telegram_id) == str(settings.ADMIN)
        }
    )

    await message.answer("Xush kelibsiz!")

    if created:
        await notify_admin_about_new_user(user, "Yangi user")
    else:
        await notify_admin_about_new_user(user, "User shunchaki start qilgan")

@start_router.message(Command("help"))
async def help_handler(message: Message):
    text = """
    /start - Botni ishga tushirish
    /help - Yordam
    /question - Savol yuborish
    /my_questions - Menim savollarim
    /cancel - Amalni bekor qilish
    """
    await message.answer(text)

def register(dp):
    dp.include_router(start_router)
