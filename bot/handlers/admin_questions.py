"""Admin-only: browse unanswered questions."""

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.filters import IsAdmin
from bot.keyboards import paginated_keyboard, parse_id
from bot.notifications import answer_keyboard
from bot.utils.telegram import CAPTION_MAX_LENGTH, MESSAGE_MAX_LENGTH, display_name, escape, safe_call, truncate
from core.models import Question

admin_questions_router = Router(name="admin_questions")
admin_questions_router.message.filter(IsAdmin())
admin_questions_router.callback_query.filter(IsAdmin())

PAGE_SIZE = 10
LIST_TITLE = "📋 Javob berilmagan savollar (eng yangilari birinchi):"


async def pending_page(page: int) -> tuple[list[Question], int]:
    qs = Question.objects.filter(is_answered=False).order_by("-created_at")
    total = await qs.acount()
    offset = (page - 1) * PAGE_SIZE
    return [q async for q in qs[offset : offset + PAGE_SIZE]], total


def pending_keyboard(questions: list[Question], page: int, total: int) -> InlineKeyboardMarkup:
    return paginated_keyboard(
        [
            (
                f"{'🔒 ' if q.in_progress else ''}#{q.pk} {truncate(q.text or '(Matnsiz savol)', 20)}",
                f"view_pending_q_{q.pk}",
            )
            for q in questions
        ],
        page=page,
        total=total,
        page_size=PAGE_SIZE,
        nav_prefix="pnav_",
    )


@admin_questions_router.message(Command("pending_questions"))
async def list_pending_questions(message: Message) -> None:
    questions, total = await pending_page(1)
    if not questions:
        await message.answer("✅ Barcha savollarga javob berilgan.")
        return
    await message.answer(LIST_TITLE, reply_markup=pending_keyboard(questions, 1, total))


@admin_questions_router.callback_query(F.data.startswith("pnav_"))
async def paginate_pending(call: CallbackQuery) -> None:
    page = max(parse_id(call.data) or 1, 1)
    questions, total = await pending_page(page)
    await safe_call(
        call.message.edit_text(LIST_TITLE, reply_markup=pending_keyboard(questions, page, total)),
        chat_id=call.from_user.id,
    )
    await call.answer()


@admin_questions_router.callback_query(F.data.startswith("view_pending_q_"))
async def show_pending_question_detail(call: CallbackQuery, bot: Bot) -> None:
    question = await Question.objects.select_related("user").filter(pk=parse_id(call.data)).afirst()
    if question is None:
        await call.answer("❗ Savol topilmadi.", show_alert=True)
        return
    if question.is_answered:
        await call.answer("❗ Bu savolga allaqachon javob berilgan.", show_alert=True)
        return
    await call.answer()

    user = question.user
    header = f"📝 <b>Savol #{question.pk}</b>\n"
    footer = (
        f"\n\n<b>Foydalanuvchi:</b> {escape(display_name(user))} (ID: <code>{user.telegram_id}</code>)"
        f"\n<b>Sana:</b> {question.created_at:%Y-%m-%d %H:%M}"
    )
    if question.in_progress:
        footer += "\n<b>Holati:</b> boshqa admin javob yozmoqda"

    markup = answer_keyboard(question.pk)
    chat_id = call.from_user.id
    if question.image_file_id or question.document_file_id:
        caption = header + escape(truncate(question.text or "", CAPTION_MAX_LENGTH - 250)) + footer
        method = bot.send_photo if question.image_file_id else bot.send_document
        await method(chat_id, question.image_file_id or question.document_file_id, caption=caption, reply_markup=markup)
    else:
        text = header + escape(truncate(question.text or "", MESSAGE_MAX_LENGTH - 250)) + footer
        await bot.send_message(chat_id, text, reply_markup=markup)
