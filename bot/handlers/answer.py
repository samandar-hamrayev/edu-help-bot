# handlers/answer.py — Aiogram FSM bilan admin javoblari
from aiogram import Router, types, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto, InputMediaDocument, InputMediaAudio
from core.models import Answer, Question, TelegramUser
from django.utils import timezone
from asgiref.sync import sync_to_async

answer_router = Router()

class AnswerStates(StatesGroup):
    collecting = State()

@answer_router.callback_query(F.data.startswith("answer_q_"))
async def start_answering(call: CallbackQuery, state: FSMContext):
    question_id = int(call.data.split("_")[-1])
    question = await sync_to_async(Question.objects.get)(id=question_id)

    if question.is_answered:
        await call.answer("❗ Bu savolga allaqachon javob berilgan.", show_alert=True)
        return

    if question.in_progress:
        await call.answer("⏳ Boshqa admin hozir bu savolni ko‘rib chiqmoqda.", show_alert=True)
        return

    question.in_progress = True
    await sync_to_async(question.save)()

    await state.set_state(AnswerStates.collecting)
    await state.set_data({
        "question_id": question_id,
        "texts": [],
        "media": []
    })
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yuborish", callback_data="send_answer")]
    ])
    await call.message.answer("📝 Javob yozing (matn, media...). Har bir qismdan keyin Yuborish tugmasi bilan yakunlang:", reply_markup=markup)
    await call.answer()

@answer_router.message(StateFilter(AnswerStates.collecting), F.content_type.in_(["text", "photo", "voice", "video", "document"]))
async def collect_media(message: types.Message, state: FSMContext):
    data = await state.get_data()

    if message.text:
        data['texts'].append(message.text)
    elif message.photo:
        data['media'].append({"type": "photo", "file_id": message.photo[-1].file_id, "caption": message.caption})
    elif message.video:
        data['media'].append({"type": "video", "file_id": message.video.file_id, "caption": message.caption})
    elif message.voice:
        data['media'].append({"type": "voice", "file_id": message.voice.file_id})
    elif message.document:
        data['media'].append({"type": "document", "file_id": message.document.file_id, "caption": message.caption})

    await state.set_data(data)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yuborish", callback_data="send_answer")]
    ])
    await message.answer("✅ Qabul qilindi. Davom eting yoki yakunlash uchun tugmani bosing:", reply_markup=markup)

@answer_router.callback_query(F.data == "send_answer", StateFilter(AnswerStates.collecting))
async def send_all_to_user(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    question = await sync_to_async(Question.objects.get)(id=data['question_id'])
    user = await sync_to_async(lambda: question.user)()

    admin_user, _ = await sync_to_async(TelegramUser.objects.get_or_create)(
        telegram_id=call.from_user.id,
        defaults={
            'username': call.from_user.username,
            'first_name': call.from_user.first_name,
            'is_admin': True
        }
    )

    for text in data['texts']:
        await bot.send_message(user.telegram_id, f"📬 Javob:\n{text}")

    for media in data['media']:
        t = media['type']
        file_id = media['file_id']
        caption = media.get('caption')
        if t == 'photo':
            await bot.send_photo(user.telegram_id, file_id, caption=caption)
        elif t == 'video':
            await bot.send_video(user.telegram_id, file_id, caption=caption)
        elif t == 'voice':
            await bot.send_voice(user.telegram_id, file_id)
        elif t == 'document':
            await bot.send_document(user.telegram_id, file_id, caption=caption)

    await sync_to_async(Answer.objects.create)(
        question=question,
        responder=admin_user,
        text="\n\n".join(data['texts']) if data['texts'] else None,
        image_file_id=next((m['file_id'] for m in data['media'] if m['type'] == 'photo'), None),
        document_file_id=next((m['file_id'] for m in data['media'] if m['type'] == 'document'), None),
        voice_file_id=next((m['file_id'] for m in data['media'] if m['type'] == 'voice'), None),
        created_at=timezone.now()
    )

    question.is_answered = True
    question.in_progress = False
    await sync_to_async(question.save)()

    await call.message.answer("✅ Javob yuborildi!")
    await state.clear()

def register(dp):
    dp.include_router(answer_router)
