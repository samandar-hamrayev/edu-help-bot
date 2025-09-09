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
            'is_admin': str(telegram_id) in settings.ADMINS
        }
    )

    welcome_text = (
        "🌟 Xush kelibsiz! Bu bot orqali savollaringizni yuborishingiz va javob olishingiz mumkin.\n\n"
        "Quyidagi buyruqlar mavjud:\n"
        "/question - Yangi savol yuborish\n"
        "/my_questions - Sizning savollaringiz ro'yxati\n"
        "/help - Yordam va qo'llanma\n"
        "/cancel - Joriy amalni bekor qilish"
    )
    await message.answer(welcome_text)

    if created:
        await notify_admin_about_new_user(user, "Yangi foydalanuvchi qo'shildi")
    else:
        await notify_admin_about_new_user(user, "Foydalanuvchi botni qayta ishga tushirdi")

# bot/start.py (update help if needed)
@start_router.message(Command("help"))
async def help_handler(message: Message):
    help_text = (
        "📘 Yordam bo'limi:\n\n"
        "/start - Botni ishga tushirish va salomlashish\n"
        "/question - Savol yuborish (matn, rasm yoki hujjat bilan)\n"
        "/my_questions - Oldingi savollaringizni ko'rish va javoblarni tekshirish\n"
        "/pending_questions - Javob berilmagan savollar ro'yxati (faqat adminlar uchun)\n"  # Add this
        "/cancel - Har qanday joriy jarayonni to'xtatish\n\n"
        "Savol yuborishda: Avval media (rasm yoki hujjat) tanlang, keyin matn yozing va tasdiqlang.\n"
        "Javoblar tez orada keladi! 😊"
    )
    await message.answer(help_text)

def register(dp):
    dp.include_router(start_router)