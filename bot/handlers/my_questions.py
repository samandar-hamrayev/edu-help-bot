from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.keyboards import paginated_keyboard, parse_id
from bot.utils.telegram import CAPTION_MAX_LENGTH, MESSAGE_MAX_LENGTH, escape, safe_call, send_content, truncate
from core.models import Answer, Question

my_questions_router = Router(name="my_questions")

PAGE_SIZE = 10
LIST_TITLE = "📋 Sizning savollaringiz (eng yangilari birinchi):"


async def user_questions_page(telegram_id: int, page: int) -> tuple[list[Question], int]:
    qs = Question.objects.filter(user__telegram_id=telegram_id).order_by("-created_at")
    total = await qs.acount()
    offset = (page - 1) * PAGE_SIZE
    return [q async for q in qs[offset : offset + PAGE_SIZE]], total


def questions_keyboard(questions: list[Question], page: int, total: int) -> InlineKeyboardMarkup:
    return paginated_keyboard(
        [
            (f"{'✅' if q.is_answered else '⏳'} {truncate(q.text or '(Matnsiz savol)', 24)}", f"qdetail_{q.pk}")
            for q in questions
        ],
        page=page,
        total=total,
        page_size=PAGE_SIZE,
        nav_prefix="qnav_",
    )


@my_questions_router.message(Command("my_questions"))
async def list_user_questions(message: Message) -> None:
    questions, total = await user_questions_page(message.from_user.id, 1)
    if not questions:
        await message.answer("⚠️ Siz hali hech qanday savol yubormagansiz. /question bilan boshlang!")
        return
    await message.answer(LIST_TITLE, reply_markup=questions_keyboard(questions, 1, total))


@my_questions_router.callback_query(F.data.startswith("qnav_"))
async def paginate_questions(call: CallbackQuery) -> None:
    page = max(parse_id(call.data) or 1, 1)
    questions, total = await user_questions_page(call.from_user.id, page)
    await safe_call(
        call.message.edit_text(LIST_TITLE, reply_markup=questions_keyboard(questions, page, total)),
        chat_id=call.from_user.id,
    )
    await call.answer()


@my_questions_router.callback_query(F.data.startswith("qdetail_"))
async def show_question_detail(call: CallbackQuery, bot: Bot) -> None:
    question_id = parse_id(call.data)
    # Filtering by owner in the query itself: other users' ids simply "don't exist".
    question = await Question.objects.filter(pk=question_id, user__telegram_id=call.from_user.id).afirst()
    if question is None:
        await call.answer("⚠️ Savol topilmadi.", show_alert=True)
        return
    await call.answer()

    chat_id = call.from_user.id
    header = f"📝 <b>Savol (ID: {question.pk})</b>\n"
    footer = f"\n\n<b>Sana:</b> {question.created_at:%Y-%m-%d %H:%M}"
    if question.image_file_id or question.document_file_id:
        caption = header + escape(truncate(question.text or "", CAPTION_MAX_LENGTH - 200)) + footer
        method = bot.send_photo if question.image_file_id else bot.send_document
        await method(chat_id, question.image_file_id or question.document_file_id, caption=caption)
    else:
        await bot.send_message(
            chat_id, header + escape(truncate(question.text or "", MESSAGE_MAX_LENGTH - 200)) + footer
        )

    answers = [a async for a in Answer.objects.filter(question=question).order_by("created_at")]
    if not answers:
        await bot.send_message(chat_id, "⏳ Javob hali berilmagan. Kutib turing!")
        return
    await bot.send_message(chat_id, "📬 <b>Javob(lar):</b>")
    for answer in answers:
        await send_content(bot, chat_id, answer.content)
