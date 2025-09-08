from aiogram import Bot
from core.models import TelegramUser
from django.conf import settings

async def notify_admin_about_new_user(user: TelegramUser, message: str = None):
    if hasattr(settings, "ADMIN"):
        from ..bot_instance import bot
        await bot.send_message(
            settings.ADMIN,
            f"{message.capitalize()}: <a href='tg://user?id={user.telegram_id}'>{user.first_name}</a>",
            parse_mode="HTML"
        )