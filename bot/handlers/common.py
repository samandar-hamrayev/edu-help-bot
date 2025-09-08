from aiogram import Router, types, F
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
    data = await state.get_data()

    if not current_state:
        await message.answer("⛔ Hech qanday amal bajarilmayapti.")
        return

    if current_state.startswith(AnswerStates.collecting.state):
        question_id = data.get("question_id")
        if question_id:
            question = await sync_to_async(Question.objects.get)(id=question_id)
            question.in_progress = False
            await sync_to_async(question.save)()
        await message.answer("✋ Javob berish bekor qilindi.")

    elif current_state.startswith(QuestionStates.choose_image.state) or \
            current_state.startswith(QuestionStates.awaiting_photo.state) or \
            current_state.startswith(QuestionStates.awaiting_text.state) or \
            current_state.startswith(QuestionStates.confirm.state):
        await message.answer("❌ Savol yuborish bekor qilindi.")

    else:
        await message.answer("⛔ Amal bekor qilindi.")

    await state.clear()

def register(dp):
    dp.include_router(common_router)
