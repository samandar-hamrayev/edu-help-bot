from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from core.models import Question, TelegramUser
from asgiref.sync import sync_to_async
from aiogram.utils.markdown import hbold, hitalic

admin_questions_router = Router()

QUESTIONS_PER_PAGE = 10

@admin_questions_router.message(Command("pending_questions"))
async def list_pending_questions(message: types.Message):
    user_id = message.from_user.id
    user = await sync_to_async(TelegramUser.objects.get)(telegram_id=user_id)
    if not user.is_admin:
        await message.answer("⚠️ Siz admin emassiz. Ushbu buyruq faqat adminlar uchun.")
        return

    total = await sync_to_async(Question.objects.filter(is_answered=False).count)()
    questions = await sync_to_async(list)(
        Question.objects.filter(is_answered=False).select_related('user').order_by('-created_at')[:QUESTIONS_PER_PAGE]
    )

    if not questions:
        await message.answer("✅ Barcha savollar javoblangan. Yangi savollar yo'q.")
        return

    keyboard = generate_pending_page_keyboard(questions, page=1, total=total)
    await message.answer("📋 Javob berilmagan savollar ro'yxati (eng yangilari birinchi):", reply_markup=keyboard)

def generate_pending_page_keyboard(questions, page, total):
    buttons = []
    for q in questions:
        status = "🔒" if q.in_progress else ""
        text_preview = q.text[:20] + "..." if q.text else "(Matnsiz savol)"
        button_text = f"{status} ID: {q.id} - {text_preview}"
        buttons.append(
            InlineKeyboardButton(text=button_text, callback_data=f"view_pending_q_{q.id}")
        )

    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]  # 2 buttons per row

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Oldingi sahifa", callback_data=f"pnav_{page-1}"))
    if page * QUESTIONS_PER_PAGE < total:
        nav_buttons.append(InlineKeyboardButton(text="Keyingi sahifa ➡️", callback_data=f"pnav_{page+1}"))

    if nav_buttons:
        rows.append(nav_buttons)

    return InlineKeyboardMarkup(inline_keyboard=rows)

@admin_questions_router.callback_query(F.data.startswith("pnav_"))
async def paginate_pending(call: CallbackQuery):
    page = int(call.data.split("_")[-1])
    offset = (page - 1) * QUESTIONS_PER_PAGE

    questions = await sync_to_async(list)(
        Question.objects.filter(is_answered=False).select_related('user').order_by('-created_at')[offset:offset + QUESTIONS_PER_PAGE]
    )
    total = await sync_to_async(Question.objects.filter(is_answered=False).count)()

    keyboard = generate_pending_page_keyboard(questions, page=page, total=total)
    await call.message.edit_text("📋 Javob berilmagan savollar ro'yxati (eng yangilari birinchi):", reply_markup=keyboard)
    await call.answer()

@admin_questions_router.callback_query(F.data.startswith("view_pending_q_"))
async def show_pending_question_detail(call: CallbackQuery, bot: Bot):
    question_id = int(call.data.split("_")[-1])
    question = await sync_to_async(Question.objects.select_related('user').get)(id=question_id)

    if question.is_answered:
        await call.answer("❗ Bu savol allaqachon javoblangan.", show_alert=True)
        return

    user = question.user
    caption = f"{hbold('📝 Savol (ID:')} {question.id}{hbold('):')}\n{question.text or hitalic('Matn yo‘q')}\n\n"
    caption += f"{hbold('Foydalanuvchi:')} {user.first_name or user.username or 'Anonim'} (ID: {user.telegram_id})\n"
    caption += f"{hbold('Sana:')} {question.created_at.strftime('%Y-%m-%d %H:%M')}\n"
    if question.in_progress:
        caption += f"{hbold('Holati:')} Ko'rib chiqilmoqda (boshqa admin tomonidan)\n"

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Javob berish", callback_data=f"answer_q_{question.id}")]
    ])

    media_sent = False
    if question.image_file_id:
        await bot.send_photo(call.from_user.id, question.image_file_id, caption=caption, reply_markup=markup, parse_mode="HTML")
        media_sent = True
    elif question.document_file_id:
        await bot.send_document(call.from_user.id, question.document_file_id, caption=caption, reply_markup=markup, parse_mode="HTML")
        media_sent = True

    if not media_sent:
        await bot.send_message(call.from_user.id, caption, reply_markup=markup, parse_mode="HTML")

    await call.answer()

def register(dp):
    dp.include_router(admin_questions_router)