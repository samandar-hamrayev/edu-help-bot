from bot.handlers.start import start_router
from bot.handlers.question import question_router
from bot.handlers.answer import answer_router
from bot.handlers.my_questions import my_questions_router
from bot.handlers.common import common_router
from bot.handlers.admin_questions import admin_questions_router
from bot.handlers.admin import admin_router
from bot.middlewares import MembershipMiddleware

def register_routers(dp):
    # let's add middleware
    dp.message.middleware(MembershipMiddleware())
    dp.callback_query.middleware(MembershipMiddleware())

    # let's register routers
    dp.include_router(start_router)
    dp.include_router(question_router)
    dp.include_router(answer_router)
    dp.include_router(my_questions_router)
    dp.include_router(common_router)
    dp.include_router(admin_questions_router)
    dp.include_router(admin_router)