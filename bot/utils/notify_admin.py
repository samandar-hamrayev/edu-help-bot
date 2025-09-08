from django.conf import settings
from core.models import TelegramUser

async def notify_admin_about_new_user(user: TelegramUser, message: str = None):
    if hasattr(settings, "ADMIN"):
        from ..bot_instance import bot
        await bot.send_message(
            settings.ADMIN,
            f"🔔 {message}: <a href='tg://user?id={user.telegram_id}'>{user.first_name or user.username}</a>\n"
            f"ID: {user.telegram_id} | Til: {user.language_code}",
            parse_mode="HTML"
        )