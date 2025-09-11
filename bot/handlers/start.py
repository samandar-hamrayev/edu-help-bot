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
        "👋 <b>Xush kelibsiz!</b>\n\n"
        "Bu savol-javob boti orqali siz:\n"
        "• 📩 Savollar yuborishingiz mumkin\n"
        "• 📨 Adminlardan javob olishingiz mumkin\n"
        "• 📊 Savollaringiz tarixini ko'rishingiz mumkin\n\n"

        "🚀 <b>Boshlash uchun:</b>\n"
        "• /question - Yangi savol yuborish\n"
        "• /help - Yordam olish\n\n"

        "⚡ <i>Botdan to'liq foydalanish uchun kerakli kanallarga a'zo bo'lishingiz talab etiladi</i>"
    )

    await message.answer(welcome_text, parse_mode="HTML")

    if created:
        await notify_admin_about_new_user(user, "Yangi foydalanuvchi qo'shildi")
    else:
        await notify_admin_about_new_user(user, "Foydalanuvchi botni qayta ishga tushirdi")


@start_router.message(Command("help"))
async def help_handler(message: Message):
    telegram_id = message.from_user.id

    is_admin = await sync_to_async(
        TelegramUser.objects.filter(telegram_id=telegram_id, is_admin=True).exists
    )()

    if is_admin:
        help_text = (
            "👑 <b>Admin paneli - Yordam bo'limi</b>\n\n"
            "🔹 <b>Foydalanuvchi buyruqlari:</b>\n"
            "• /question - Yangi savol yuborish\n"
            "• /my_questions - Mening savollarim\n"
            "• /cancel - Joriy amalni bekor qilish\n"
            "• /help - Yordam ma'lumotlari\n\n"

            "🔹 <b>Admin buyruqlari:</b>\n"
            "• /pending_questions - Javob berilmagan savollar\n"
            "• /stats - Bot statistikasi\n"
            "• /broadcast - Hammaga xabar yuborish\n"

            "🔹 <b>Admin funksiyalari:</b>\n"
            "• 📥 Yangi savollarni ko'rish\n"
            "• 📤 Savollarga javob yozish\n"

            "📞 <i>Boshqa adminlar bilan bog'lanish uchun guruhdan foydalaning</i>"
        )
    else:
        help_text = (
            "🤖 <b>Botdan foydalanish bo'yicha yo'riqnoma</b>\n\n"
            "🔹 <b>Asosiy buyruqlar:</b>\n"
            "• /start - Botni ishga tushirish\n"
            "• /question - Yangi savol yuborish\n"
            "• /my_questions - Mening savollarim\n"
            "• /cancel - Joriy amalni bekor qilish\n"
            "• /help - Yordam ma'lumotlari\n\n"

            "🔹 <b>Qanday ishlaydi?</b>\n"
            "1. /question buyrug'i bilan savol yuboring\n"
            "2. Adminlar savolingizni ko'radi va javob beradi\n"
            "3. Javobni shaxsiy xabarda olasiz\n"
            "4. /my_questions bilan tarixni ko'rishingiz mumkin\n\n"

            "📝 <b>Savol yuborish:</b>\n"
            "• Matn, rasm yoki fayl shaklida savol yuborishingiz mumkin\n"
            "• Har bir savol alohida qayd etiladi\n"
            "• Adminlar tez orada javob beradi\n\n"

            "⏰ <b>Javob vaqti:</b>\n"
            "• Odatiy 24 soat ichida javob olasiz\n"
            "• Favqulodda holatlarda adminlarga murojaat qiling\n\n"

            "📞 <i>Qo'shimcha savollar bo'lsa, adminga murojaat qiling @Ozodbek_Jabborow</i>"
        )

    await message.answer(help_text, parse_mode="HTML")


def register(dp):
    dp.include_router(start_router)