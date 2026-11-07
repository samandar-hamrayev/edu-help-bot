from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.admin import admin_router
from bot.handlers.admin_questions import admin_questions_router
from bot.handlers.answer import answer_router
from bot.handlers.common import common_router, fallback_router
from bot.handlers.my_questions import my_questions_router
from bot.handlers.question import question_router
from bot.handlers.start import start_router
from bot.middlewares import DbConnectionMiddleware, MembershipMiddleware


def register_routers(dp: Dispatcher) -> None:
    dp.update.outer_middleware(DbConnectionMiddleware())
    dp.message.middleware(MembershipMiddleware())
    dp.callback_query.middleware(MembershipMiddleware())

    # Order matters: /start and /cancel must win over state handlers that
    # would otherwise swallow the message; admin routers are IsAdmin-filtered.
    dp.include_routers(
        start_router,
        common_router,
        admin_router,
        admin_questions_router,
        answer_router,
        question_router,
        my_questions_router,
        fallback_router,
    )


def build_dispatcher(storage: BaseStorage | None = None) -> Dispatcher:
    dp = Dispatcher(storage=storage or MemoryStorage())
    register_routers(dp)
    return dp
