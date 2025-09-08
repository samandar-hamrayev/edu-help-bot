# dispatcher.py
from bot.handlers.start import start_router
from bot.handlers.question import question_router
from bot.handlers.answer import answer_router

def register_routers(dp):
    dp.include_router(start_router)
    dp.include_router(question_router)
    dp.include_router(answer_router)
