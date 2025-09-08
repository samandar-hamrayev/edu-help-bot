from aiogram import Router, types, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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
        await call.answer("❗ Bu savolga allaqachon javob berilgan. Boshqa savollarni ko'ring.", show_alert=True)
        return

    if question.in_progress:
        await call.answer("⏳ Bu savol ustida boshqa admin ishlamoqda. Kutib turing yoki boshqasini tanlang.", show_alert=True)
        return

    question.in_progress = True
    await sync_to_async(question.save)()

    await state.set_state(AnswerStates.collecting)
    await state.set_data({
        "question_id": question_id,
        "content": []  # List for all parts
    })
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Javobni yuborish", callback_data="send_answer")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_answer")]
    ])
    await call.message.answer(
        "📝 Javobni shakllantiring: Matn yozing, rasm, video, ovoz yoki hujjat yuboring.\n"
        "Bir necha qism qo'shishingiz mumkin. Tayyor bo'lganda 'Yuborish' ni bosing.",
        reply_markup=markup
    )
    await call.answer()

@answer_router.message(StateFilter(AnswerStates.collecting), F.content_type.in_(["text", "photo", "voice", "video", "document"]))
async def collect_media(message: types.Message, state: FSMContext):
    data = await state.get_data()
    content = data['content']

    if message.text:
        content.append({"type": "text", "text": message.text})
    elif message.photo:
        content.append({"type": "photo", "file_id": message.photo[-1].file_id, "caption": message.caption})
    elif message.video:
        content.append({"type": "video", "file_id": message.video.file_id, "caption": message.caption})
    elif message.voice:
        content.append({"type": "voice", "file_id": message.voice.file_id})
    elif message.document:
        content.append({"type": "document", "file_id": message.document.file_id, "caption": message.caption})

    await state.set_data(data)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Javobni yuborish", callback_data="send_answer")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_answer")]
    ])
    await message.answer("✅ Qism qo'shildi. Davom eting yoki yuboring:", reply_markup=markup)

@answer_router.callback_query(F.data == "cancel_answer", StateFilter(AnswerStates.collecting))
async def cancel_answering(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    question_id = data.get("question_id")
    if question_id:
        question = await sync_to_async(Question.objects.get)(id=question_id)
        question.in_progress = False
        await sync_to_async(question.save)()
    await call.message.answer("❌ Javob berish bekor qilindi.")
    await state.clear()
    await call.answer()

@answer_router.callback_query(F.data == "send_answer", StateFilter(AnswerStates.collecting))
async def send_all_to_user(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if not data.get('content'):
        await call.answer("⚠️ Hech qanday kontent qo'shilmagan. Iltimos, qaytadan boshlang.", show_alert=True)
        return

    # Prefetch user with select_related
    question = await sync_to_async(Question.objects.select_related('user').get)(id=data['question_id'])
    user = question.user

    # Get or create admin_user
    admin_user, _ = await sync_to_async(TelegramUser.objects.get_or_create)(
        telegram_id=call.from_user.id,
        defaults={
            'username': call.from_user.username,
            'first_name': call.from_user.first_name,
            'last_name': call.from_user.last_name,
            'language_code': call.from_user.language_code,
            'is_admin': True
        }
    )

    # Send to user
    await bot.send_message(user.telegram_id, "📬 Sizning savolingizga javob keldi:")
    for item in data['content']:
        item_type = item.get('type')
        if item_type == 'text':
            await bot.send_message(user.telegram_id, item['text'])
        elif item_type == 'photo':
            await bot.send_photo(user.telegram_id, item['file_id'], caption=item.get('caption'))
        elif item_type == 'video':
            await bot.send_video(user.telegram_id, item['file_id'], caption=item.get('caption'))
        elif item_type == 'voice':
            await bot.send_voice(user.telegram_id, item['file_id'])
        elif item_type == 'document':
            await bot.send_document(user.telegram_id, item['file_id'], caption=item.get('caption'))

    # Save to DB
    await sync_to_async(Answer.objects.create)(
        question=question,
        responder=admin_user,
        content=data['content'],
        created_at=timezone.now()
    )

    question.is_answered = True
    question.in_progress = False
    await sync_to_async(question.save)()

    await call.message.answer("✅ Javob muvaffaqiyatli yuborildi va saqlandi!")
    await state.clear()
    await call.answer()

def register(dp):
    dp.include_router(answer_router)