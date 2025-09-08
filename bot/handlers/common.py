from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from core.models import Question
from asgiref.sync import sync_to_async
from bot.handlers.answer import AnswerStates
from bot.handlers.question import QuestionStates

common_router = Router()

@common_router.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()

    if not current_state:
        await message.answer("ℹ️ Hozirda hech qanday jarayon faol emas. /start bilan boshlang.")
        return

    if current_state in AnswerStates.__states__:
        data = await state.get_data()
        question_id = data.get("question_id")
        if question_id:
            question = await sync_to_async(Question.objects.get)(id=question_id)
            question.in_progress = False
            await sync_to_async(question.save)()
        await message.answer("✋ Javob berish jarayoni bekor qilindi.")

    elif current_state in QuestionStates.__states__:
        await message.answer("❌ Savol yuborish jarayoni bekor qilindi.")

    else:
        await message.answer("ℹ️ Joriy jarayon bekor qilindi.")

    await state.clear()

def register(dp):
    dp.include_router(common_router)