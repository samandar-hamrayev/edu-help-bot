from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from core.models import Question, Answer
from asgiref.sync import sync_to_async
from aiogram.utils.markdown import hbold, hitalic

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
        await message.answer("⚠️ Siz hali hech qanday savol yubormagansiz. /question bilan boshlang!")
        return

    keyboard = generate_question_page_keyboard(questions, page=1, total=total)
    await message.answer("📋 Sizning savollaringiz ro'yxati (eng yangilari birinchi):", reply_markup=keyboard)

def generate_question_page_keyboard(questions, page, total):
    buttons = []
    for i, q in enumerate(questions):
        status = "✅" if q.is_answered else "⏳"
        text_preview = q.text[:20] + "..." if q.text else "(Matnsiz savol)"
        button_text = f"{status} {text_preview}"
        buttons.append(
            InlineKeyboardButton(text=button_text, callback_data=f"qdetail_{q.id}")
        )

    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Oldingi sahifa", callback_data=f"qnav_{page-1}"))
    if page * QUESTIONS_PER_PAGE < total:
        nav_buttons.append(InlineKeyboardButton(text="Keyingi sahifa ➡️", callback_data=f"qnav_{page+1}"))

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
    await call.message.edit_text("📋 Sizning savollaringiz ro'yxati (eng yangilari birinchi):", reply_markup=keyboard)
    await call.answer()

@my_questions_router.callback_query(F.data.startswith("qdetail_"))
async def show_question_detail(call: CallbackQuery, bot: Bot):
    question_id = int(call.data.split("_")[-1])
    # Prefetch user
    question = await sync_to_async(Question.objects.select_related('user').get)(id=question_id)

    if question.user.telegram_id != call.from_user.id:
        await call.answer("⚠️ Bu savol sizga tegishli emas!", show_alert=True)
        return

    caption = f"{hbold('📝 Savol (ID: ' + str(question.id) + '):')}\n{question.text or hitalic('Matn yo‘q')}\n\n{hbold('Sana:')} {question.created_at.strftime('%Y-%m-%d %H:%M')}"

    media_sent = False
    if question.image_file_id:
        await bot.send_photo(call.from_user.id, question.image_file_id, caption=caption, parse_mode="HTML")
        media_sent = True
    elif question.document_file_id:
        await bot.send_document(call.from_user.id, question.document_file_id, caption=caption, parse_mode="HTML")
        media_sent = True

    if not media_sent:
        await bot.send_message(call.from_user.id, caption, parse_mode="HTML")

    if question.is_answered:
        answers = await sync_to_async(list)(Answer.objects.filter(question=question))
        if answers:
            await bot.send_message(call.from_user.id, hbold("📬 Javob(lar):"), parse_mode="HTML")
            for answer in answers:
                for item in answer.content:
                    item_type = item.get('type')
                    if item_type == 'text':
                        await bot.send_message(call.from_user.id, item['text'])
                    elif item_type == 'photo':
                        await bot.send_photo(call.from_user.id, item['file_id'], caption=item.get('caption'))
                    elif item_type == 'video':
                        await bot.send_video(call.from_user.id, item['file_id'], caption=item.get('caption'))
                    elif item_type == 'voice':
                        await bot.send_voice(call.from_user.id, item['file_id'])
                    elif item_type == 'document':
                        await bot.send_document(call.from_user.id, item['file_id'], caption=item.get('caption'))
        else:
            await bot.send_message(call.from_user.id, "⚠️ Javob topilmadi, lekin savol belgilangan.")
    else:
        await bot.send_message(call.from_user.id, "⏳ Javob hali berilmagan. Kutib turing!")

    await call.answer()

def register(dp):
    dp.include_router(my_questions_router)