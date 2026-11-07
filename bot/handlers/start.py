from aiogram import Bot, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from django.conf import settings

from bot.notifications import notify_admins_new_user
from bot.utils.telegram import escape
from core.services import TelegramProfile, is_admin, upsert_telegram_user

start_router = Router(name="start")

WELCOME_TEXT = (
    "👋 <b>Xush kelibsiz!</b>\n\n"
    "Bu savol-javob boti orqali siz:\n"
    "• 📩 Savollar yuborishingiz mumkin\n"
    "• 📨 Adminlardan javob olishingiz mumkin\n"
    "• 📊 Savollaringiz tarixini ko'rishingiz mumkin\n\n"
    "🚀 <b>Boshlash uchun:</b>\n"
    "• /question - Yangi savol yuborish\n"
    "• /help - Yordam olish"
)

ADMIN_HELP_TEXT = (
    "👑 <b>Admin paneli - Yordam bo'limi</b>\n\n"
    "🔹 <b>Foydalanuvchi buyruqlari:</b>\n"
    "• /question - Yangi savol yuborish\n"
    "• /my_questions - Mening savollarim\n"
    "• /cancel - Joriy amalni bekor qilish\n"
    "• /help - Yordam ma'lumotlari\n\n"
    "🔹 <b>Admin buyruqlari:</b>\n"
    "• /pending_questions - Javob berilmagan savollar\n"
    "• /stats - Bot statistikasi\n\n"
    "🔹 <b>Admin funksiyalari:</b>\n"
    "• 📥 Yangi savollar haqida xabar olish\n"
    "• 📤 «Javob berish» tugmasi orqali javob yozish"
)

USER_HELP_TEXT = (
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
    "📝 Savolga rasm yoki hujjat biriktirishingiz mumkin."
)


@start_router.message(CommandStart())
async def start_handler(message: Message, bot: Bot) -> None:
    user, created = await upsert_telegram_user(TelegramProfile.from_aiogram(message.from_user))
    text = WELCOME_TEXT
    if settings.REQUIRED_CHATS:
        text += "\n\n⚡ <i>Botdan foydalanish uchun kerakli kanallarga a'zo bo'lishingiz talab etiladi</i>"
    await message.answer(text)
    if created:
        await notify_admins_new_user(bot, user)


@start_router.message(Command("help"))
async def help_handler(message: Message) -> None:
    if await is_admin(message.from_user.id):
        await message.answer(ADMIN_HELP_TEXT)
        return
    text = USER_HELP_TEXT
    if settings.SUPPORT_CONTACT:
        text += f"\n\n📞 <i>Qo'shimcha savollar bo'lsa: {escape(settings.SUPPORT_CONTACT)}</i>"
    await message.answer(text)
