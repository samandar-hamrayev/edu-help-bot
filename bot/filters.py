from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from core.services import is_admin


class IsAdmin(Filter):
    """Pass only for Telegram admins (``TELEGRAM_ADMINS`` env var or ``is_admin`` in the DB)."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return user is not None and await is_admin(user.id)
