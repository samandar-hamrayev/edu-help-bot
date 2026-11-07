"""Admin flow: claim a question, collect a multi-part answer, deliver it."""

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from django.core.exceptions import ValidationError

from bot.delivery import deliver_answer
from bot.filters import IsAdmin
from bot.keyboards import parse_id
from core.models import ANSWER_TEXT_MAX_LENGTH
from core.services import (
    CAPTION_MAX_LENGTH,
    MAX_ANSWER_PARTS,
    ClaimResult,
    TelegramProfile,
    acreate_answer,
    claim_question,
    release_question,
    upsert_telegram_user,
)

logger = logging.getLogger(__name__)

answer_router = Router(name="answer")
answer_router.message.filter(IsAdmin())
answer_router.callback_query.filter(IsAdmin())


class AnswerStates(StatesGroup):
    collecting = State()


ANSWER_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="✅ Javobni yuborish", callback_data="send_answer")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_answer")],
    ]
)

CLAIM_ERRORS = {
    ClaimResult.NOT_FOUND: "❗ Savol topilmadi.",
    ClaimResult.ALREADY_ANSWERED: "❗ Bu savolga allaqachon javob berilgan.",
    ClaimResult.LOCKED: "⏳ Bu savol ustida boshqa admin ishlamoqda.",
}


def message_to_part(message: Message) -> dict | None:
    if message.text:
        return {"type": "text", "text": message.text}
    if message.photo:
        return {"type": "photo", "file_id": message.photo[-1].file_id, "caption": message.caption}
    if message.video:
        return {"type": "video", "file_id": message.video.file_id, "caption": message.caption}
    if message.voice:
        return {"type": "voice", "file_id": message.voice.file_id}
    if message.document:
        return {"type": "document", "file_id": message.document.file_id, "caption": message.caption}
    return None


@answer_router.callback_query(F.data.startswith("answer_q_"))
async def start_answering(call: CallbackQuery, state: FSMContext) -> None:
    question_id = parse_id(call.data)
    if question_id is None:
        await call.answer("❗ Noto'g'ri so'rov.", show_alert=True)
        return

    previous = await state.get_data()
    if await state.get_state() == AnswerStates.collecting.state and previous.get("question_id") not in (
        None,
        question_id,
    ):
        await release_question(previous["question_id"])

    admin, _ = await upsert_telegram_user(TelegramProfile.from_aiogram(call.from_user))
    result = await claim_question(question_id, admin)
    if result is not ClaimResult.CLAIMED:
        await call.answer(CLAIM_ERRORS[result], show_alert=True)
        return

    await state.set_state(AnswerStates.collecting)
    await state.set_data({"question_id": question_id, "content": []})
    await call.message.answer(
        f"📝 Savol #{question_id} uchun javob yozing: matn, rasm, video, ovoz yoki hujjat yuboring.\n"
        "Bir necha qism qo'shishingiz mumkin. Tayyor bo'lganda «Javobni yuborish» ni bosing.",
        reply_markup=ANSWER_KEYBOARD,
    )
    await call.answer()


@answer_router.message(AnswerStates.collecting, ~F.text.startswith("/"))
async def collect_part(message: Message, state: FSMContext) -> None:
    part = message_to_part(message)
    if part is None:
        await message.answer("⚠️ Faqat matn, rasm, video, ovoz yoki hujjat qabul qilinadi.")
        return
    if part["type"] == "text" and len(part["text"]) > ANSWER_TEXT_MAX_LENGTH:
        await message.answer(f"⚠️ Matn {ANSWER_TEXT_MAX_LENGTH} belgidan oshmasligi kerak.")
        return
    if len(part.get("caption") or "") > CAPTION_MAX_LENGTH:
        await message.answer(f"⚠️ Izoh {CAPTION_MAX_LENGTH} belgidan oshmasligi kerak.")
        return

    data = await state.get_data()
    content = data.get("content", [])
    if len(content) >= MAX_ANSWER_PARTS:
        await message.answer(f"⚠️ Ko'pi bilan {MAX_ANSWER_PARTS} qism. Endi «Javobni yuborish» ni bosing.")
        return
    content.append(part)
    await state.update_data(content=content)
    await message.answer(
        f"✅ Qism qo'shildi ({len(content)}). Davom eting yoki yuboring:", reply_markup=ANSWER_KEYBOARD
    )


@answer_router.callback_query(AnswerStates.collecting, F.data == "cancel_answer")
async def cancel_answering(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("question_id"):
        await release_question(data["question_id"])
    await state.clear()
    await call.message.answer("❌ Javob berish bekor qilindi.")
    await call.answer()


@answer_router.callback_query(AnswerStates.collecting, F.data == "send_answer")
async def send_answer(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    if not data.get("content"):
        await call.answer("⚠️ Hech qanday qism qo'shilmagan.", show_alert=True)
        return

    admin, _ = await upsert_telegram_user(TelegramProfile.from_aiogram(call.from_user))
    try:
        answer = await acreate_answer(data["question_id"], data["content"], responder=admin)
    except ValidationError as exc:
        await call.answer(f"⚠️ {exc.messages[0]}", show_alert=True)
        return
    await state.clear()
    await call.answer()

    # The answer is saved; delivery problems are recorded on the Answer row and
    # transient ones are retried by the outbox loop.
    if await deliver_answer(bot, answer.pk):
        await call.message.answer("✅ Javob foydalanuvchiga yuborildi va saqlandi!")
    else:
        await answer.arefresh_from_db(fields=["delivery_status", "delivery_error"])
        if answer.delivery_status == answer.DeliveryStatus.FAILED:
            await call.message.answer(
                "⚠️ Javob saqlandi, lekin foydalanuvchiga yetkazib bo'lmadi "
                "(ehtimol botni bloklagan). Holatni admin paneldan ko'rishingiz mumkin."
            )
        else:
            await call.message.answer("🕓 Javob saqlandi; yetkazish keyinroq qayta urinib ko'riladi.")
