# handlers/my_questions.py
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from core.models import Question, Answer
from asgiref.sync import sync_to_async
from aiogram.utils.markdown import hbold

my_questions_router = Router()

QUESTIONS_PER_PAGE = 10

@my_questions_router.message(Command("my_questions"))
async def list_user_questions(message: types.Message):
    user_id = message.from_user.id
    total = await sync_to_async(Question.objects.filter(user__telegram_id=user_id).count)()
    questions = await sync_to_async(list)(
        Question.objects.filter(user__telegram_id=user_id).order_by('-created_at')[:QUESTIONS_PER_PAGE]
    )

    if not questions:
        await message.answer("Siz hali hech qanday savol yubormagansiz.")
        return

    keyboard = generate_question_page_keyboard(questions, page=1, total=total)
    await message.answer("Sizning savollaringiz:", reply_markup=keyboard)

def generate_question_page_keyboard(questions, page, total):
    buttons = []
    for i, q in enumerate(questions):
        text = f"{i+1}. {q.text[:30]}" if q.text else "(matnsiz)"
        buttons.append(
            InlineKeyboardButton(text=f"{i+1}", callback_data=f"qpage_{page}_idx_{i}")
        )

    rows = [buttons[i:i+5] for i in range(0, len(buttons), 5)]

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"qnav_{page-1}"))
    if page * QUESTIONS_PER_PAGE < total:
        nav_buttons.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"qnav_{page+1}"))

    if nav_buttons:
        rows.append(nav_buttons)

    return InlineKeyboardMarkup(inline_keyboard=rows)

@my_questions_router.callback_query(F.data.startswith("qnav_"))
async def paginate_questions(call: CallbackQuery):
    page = int(call.data.split("_")[-1])
    offset = (page - 1) * QUESTIONS_PER_PAGE

    questions = await sync_to_async(list)(
        Question.objects.filter(user__telegram_id=call.from_user.id).order_by('-created_at')[offset:offset + QUESTIONS_PER_PAGE]
    )
    total = await sync_to_async(Question.objects.filter(user__telegram_id=call.from_user.id).count)()

    keyboard = generate_question_page_keyboard(questions, page=page, total=total)
    await call.message.edit_reply_markup(reply_markup=keyboard)
    await call.answer()

@my_questions_router.callback_query(F.data.startswith("qpage_"))
async def show_question_detail(call: CallbackQuery, bot: Bot):
    parts = call.data.split("_")
    page = int(parts[1])
    idx = int(parts[3])
    offset = (page - 1) * QUESTIONS_PER_PAGE

    questions = await sync_to_async(list)(
        Question.objects.filter(user__telegram_id=call.from_user.id).order_by('-created_at')[offset:offset + QUESTIONS_PER_PAGE]
    )

    try:
        question = questions[idx]
    except IndexError:
        await call.answer("❌ Savol topilmadi.", show_alert=True)
        return

    media_sent = False
    caption = f"{hbold('Savol:')}\n{question.text or 'Matn yoq'}"

    if question.image_file_id:
        await bot.send_photo(call.from_user.id, question.image_file_id, caption=caption, parse_mode="HTML")
        media_sent = True
    elif question.document_file_id:
        await bot.send_document(call.from_user.id, question.document_file_id, caption=caption, parse_mode="HTML")
        media_sent = True
    elif question.voice_file_id:
        await bot.send_voice(call.from_user.id, question.voice_file_id, caption=caption, parse_mode="HTML")
        media_sent = True

    if not media_sent:
        await call.message.answer(caption, parse_mode="HTML")

    if question.is_answered:
        try:
            answer = await sync_to_async(Answer.objects.get)(question=question)
            await call.message.answer(hbold("Javob:"), parse_mode="HTML")
            if answer.text:
                await call.message.answer(answer.text)
            if answer.image_file_id:
                await bot.send_photo(call.from_user.id, answer.image_file_id)
            if answer.document_file_id:
                await bot.send_document(call.from_user.id, answer.document_file_id)
            if answer.voice_file_id:
                await bot.send_voice(call.from_user.id, answer.voice_file_id)
        except Answer.DoesNotExist:
            await call.message.answer("⚠️ Javob topilmadi.")

    await call.answer()

def register(dp):
    dp.include_router(my_questions_router)
