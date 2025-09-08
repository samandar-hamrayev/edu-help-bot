from aiogram import types, Router, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from core.models import TelegramUser, Question
from django.utils import timezone
from asgiref.sync import sync_to_async

question_router = Router()

class QuestionStates(StatesGroup):
    choose_image = State()
    awaiting_photo = State()
    awaiting_document = State()
    awaiting_text = State()
    confirm = State()

@question_router.message(F.text == "/question")
async def start_question_flow(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await sync_to_async(TelegramUser.objects.get_or_create)(
        telegram_id=user_id,
        defaults={
            "username": message.from_user.username,
            "first_name": message.from_user.first_name
        }
    )

    await state.set_state(QuestionStates.choose_image)
    await state.set_data({"image": None, "text": None, "document": None})

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📷 Rasm yuborish", callback_data="send_image")],
        [InlineKeyboardButton(text="📎 Hujjat yuborish", callback_data="send_document")],
        [InlineKeyboardButton(text="🚫 Mediasiz yuborish", callback_data="skip_media")]
    ])
    await message.answer("Savolingiz uchun media yubormoqchimisiz?", reply_markup=markup)

@question_router.callback_query(F.data.in_(["send_image", "send_document", "skip_media"]))
async def handle_media_choice(call: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current != QuestionStates.choose_image:
        return

    if call.data == "send_image":
        await state.set_state(QuestionStates.awaiting_photo)
        await call.message.answer("Iltimos, rasm yuboring:")
    elif call.data == "send_document":
        await state.set_state(QuestionStates.awaiting_document)
        await call.message.answer("Iltimos, hujjat yuboring:")
    else:
        await state.set_state(QuestionStates.awaiting_text)
        await call.message.answer("Endi savolingiz matnini yuboring:")

    await call.answer()

@question_router.message(F.photo, QuestionStates.awaiting_photo)
async def handle_photo(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    data = await state.get_data()
    data["image"] = file_id
    await state.set_data(data)
    await state.set_state(QuestionStates.awaiting_text)
    await message.answer("Endi savolingiz matnini yuboring:")

@question_router.message(F.document, QuestionStates.awaiting_document)
async def handle_document(message: types.Message, state: FSMContext):
    file_id = message.document.file_id
    data = await state.get_data()
    data["document"] = file_id
    await state.set_data(data)
    await state.set_state(QuestionStates.awaiting_text)
    await message.answer("Endi savolingiz matnini yuboring:")

@question_router.message(F.text, QuestionStates.awaiting_text)
async def handle_question_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    data["text"] = message.text
    await state.set_data(data)
    await state.set_state(QuestionStates.confirm)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yuborish", callback_data="confirm_send")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_question")]
    ])
    await message.answer("Savolingizni yuborishni tasdiqlaysizmi?", reply_markup=markup)

@question_router.callback_query(F.data.in_(["confirm_send", "cancel_question"]), QuestionStates.confirm)
async def finalize_question(call: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = call.from_user.id
    data = await state.get_data()

    if call.data == "cancel_question":
        await call.message.answer("❌ Savolingiz bekor qilindi.")
        await state.clear()
        return

    user = await sync_to_async(TelegramUser.objects.get)(telegram_id=user_id)
    question = await sync_to_async(Question.objects.create)(
        user=user,
        image_file_id=data.get("image"),
        document_file_id=data.get("document"),
        text=data.get("text"),
        created_at=timezone.now(),
        in_progress=False,
        is_answered=False
    )

    admins = await sync_to_async(list)(TelegramUser.objects.filter(is_admin=True))
    for admin in admins:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Javob berish", callback_data=f"answer_q_{question.id}")]
        ])
        msg = f"🆕 Yangi savol:\n\n{data.get('text') or '(matn yo‘q)'}"
        if data.get("image"):
            await bot.send_photo(admin.telegram_id, data["image"], caption=msg, reply_markup=markup)
        elif data.get("document"):
            await bot.send_document(admin.telegram_id, data["document"], caption=msg, reply_markup=markup)
        else:
            await bot.send_message(admin.telegram_id, msg, reply_markup=markup)

    await call.message.answer("✅ Savolingiz yuborildi. Tez orada javob olasiz.")
    await state.clear()

def register(dp):
    dp.include_router(question_router)
