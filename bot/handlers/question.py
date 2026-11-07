from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from django.core.exceptions import ValidationError

from bot.notifications import notify_admins_new_question
from bot.utils.telegram import escape, truncate
from core.models import QUESTION_TEXT_MAX_LENGTH
from core.services import TelegramProfile, create_question, upsert_telegram_user, validate_question_text

question_router = Router(name="question")

NOT_A_COMMAND = ~F.text.startswith("/")


class QuestionStates(StatesGroup):
    choose_media = State()
    awaiting_photo = State()
    awaiting_document = State()
    awaiting_text = State()
    confirm = State()


MEDIA_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📷 Rasm qo'shish", callback_data="add_photo")],
        [InlineKeyboardButton(text="📎 Hujjat qo'shish", callback_data="add_document")],
        [InlineKeyboardButton(text="🚫 Mediasiz davom etish", callback_data="skip_media")],
    ]
)
CONFIRM_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash va yuborish", callback_data="confirm_send")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_question")],
    ]
)
ASK_TEXT = f"Endi savolingiz matnini kiriting (ko'pi bilan {QUESTION_TEXT_MAX_LENGTH} belgi):"


@question_router.message(Command("question"))
async def start_question_flow(message: Message, state: FSMContext) -> None:
    await upsert_telegram_user(TelegramProfile.from_aiogram(message.from_user))
    await state.set_state(QuestionStates.choose_media)
    await state.set_data({"image": None, "document": None, "text": None})
    await message.answer(
        "Savolingizga media (rasm yoki hujjat) qo'shmoqchimisiz? Tanlang:", reply_markup=MEDIA_KEYBOARD
    )


@question_router.callback_query(QuestionStates.choose_media, F.data.in_({"add_photo", "add_document", "skip_media"}))
async def handle_media_choice(call: CallbackQuery, state: FSMContext) -> None:
    if call.data == "add_photo":
        await state.set_state(QuestionStates.awaiting_photo)
        await call.message.answer("Iltimos, savol bilan bog'liq rasmni yuboring:")
    elif call.data == "add_document":
        await state.set_state(QuestionStates.awaiting_document)
        await call.message.answer("Iltimos, savol bilan bog'liq hujjatni yuboring:")
    else:
        await state.set_state(QuestionStates.awaiting_text)
        await call.message.answer(ASK_TEXT)
    await call.answer()


@question_router.message(QuestionStates.awaiting_photo, F.photo)
async def handle_photo(message: Message, state: FSMContext) -> None:
    await state.update_data(image=message.photo[-1].file_id)
    await state.set_state(QuestionStates.awaiting_text)
    await message.answer("✅ Rasm qabul qilindi. " + ASK_TEXT)


@question_router.message(QuestionStates.awaiting_document, F.document)
async def handle_document(message: Message, state: FSMContext) -> None:
    await state.update_data(document=message.document.file_id)
    await state.set_state(QuestionStates.awaiting_text)
    await message.answer("✅ Hujjat qabul qilindi. " + ASK_TEXT)


@question_router.message(QuestionStates.awaiting_text, F.text, NOT_A_COMMAND)
async def handle_question_text(message: Message, state: FSMContext) -> None:
    try:
        text = validate_question_text(message.text)
    except ValidationError as exc:
        await message.answer(f"⚠️ {exc.messages[0]} Qaytadan yozing:")
        return

    data = await state.update_data(text=text)
    await state.set_state(QuestionStates.confirm)

    preview = f"📝 <b>Savolingiz:</b>\n{escape(truncate(text, 300))}\n"
    if data.get("image"):
        preview += "📷 Rasm qo'shilgan\n"
    if data.get("document"):
        preview += "📎 Hujjat qo'shilgan\n"
    await message.answer(preview + "\nYuborishni tasdiqlaysizmi?", reply_markup=CONFIRM_KEYBOARD)


@question_router.message(
    StateFilter(QuestionStates.awaiting_photo, QuestionStates.awaiting_document, QuestionStates.awaiting_text),
    NOT_A_COMMAND,
)
async def unexpected_input(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    expected = {
        QuestionStates.awaiting_photo.state: "rasm",
        QuestionStates.awaiting_document.state: "hujjat (fayl)",
        QuestionStates.awaiting_text.state: "matn",
    }.get(current, "javob")
    await message.answer(f"⚠️ Iltimos, {expected} yuboring yoki /cancel bilan bekor qiling.")


@question_router.callback_query(QuestionStates.confirm, F.data == "cancel_question")
async def cancel_question(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.answer("❌ Savol yuborish bekor qilindi. /question bilan qaytadan boshlang.")
    await call.answer()


@question_router.callback_query(QuestionStates.confirm, F.data == "confirm_send")
async def finalize_question(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    # Clear first: a double tap on "confirm" must not create two questions.
    await state.clear()
    user, _ = await upsert_telegram_user(TelegramProfile.from_aiogram(call.from_user))
    try:
        question = await create_question(user, data.get("text"), data.get("image"), data.get("document"))
    except ValidationError as exc:
        await call.message.answer(f"⚠️ {exc.messages[0]} /question bilan qaytadan boshlang.")
        await call.answer()
        return

    await notify_admins_new_question(bot, question, user)
    await call.message.answer(f"✅ Savolingiz yuborildi (ID: {question.pk})! Javob kelganda shu yerda xabar olasiz. 😊")
    await call.answer()
