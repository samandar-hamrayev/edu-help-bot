import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.answer import AnswerStates
from bot.handlers.question import QuestionStates
from bot.membership import CHECK_CALLBACK, membership_keyboard, membership_text, missing_chats
from bot.utils.telegram import safe_call
from core.services import is_admin, release_question

logger = logging.getLogger(__name__)

common_router = Router(name="common")
# Registered last: replies to admin commands that IsAdmin-filtered routers rejected.
fallback_router = Router(name="fallback")

ADMIN_COMMANDS = ("stats", "pending_questions")


@common_router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("ℹ️ Hozirda hech qanday jarayon faol emas.")
        return

    if current_state in AnswerStates.__all_states_names__:
        question_id = (await state.get_data()).get("question_id")
        if question_id:
            await release_question(question_id)
        await message.answer("✋ Javob berish jarayoni bekor qilindi.")
    elif current_state in QuestionStates.__all_states_names__:
        await message.answer("❌ Savol yuborish jarayoni bekor qilindi.")
    else:
        await message.answer("ℹ️ Joriy jarayon bekor qilindi.")
    await state.clear()
    logger.info("User %s cancelled state %s", message.from_user.id, current_state)


@common_router.callback_query(F.data == CHECK_CALLBACK)
async def check_membership_handler(call: CallbackQuery, bot: Bot) -> None:
    user_id = call.from_user.id
    missing = [] if await is_admin(user_id) else await missing_chats(bot, user_id)
    if not missing:
        await safe_call(
            call.message.edit_text(
                "✅ A'zolik tasdiqlandi!\n\n"
                "🎉 Botdan to'liq foydalanishingiz mumkin:\n"
                "• /question - Savol berish\n"
                "• /my_questions - Mening savollarim\n"
                "• /help - Yordam",
                reply_markup=None,
            ),
            chat_id=user_id,
        )
        await call.answer("✅")
        return

    await safe_call(
        call.message.edit_text(membership_text(missing), reply_markup=membership_keyboard(missing)),
        chat_id=user_id,
    )
    await call.answer("Hali barcha kanallarga a'zo bo'lmagansiz", show_alert=True)


@fallback_router.message(Command(*ADMIN_COMMANDS))
async def admin_only_handler(message: Message) -> None:
    await message.answer("❌ Bu buyruq faqat adminlar uchun!")


@fallback_router.callback_query()
async def stale_callback_handler(call: CallbackQuery) -> None:
    # Buttons from expired flows (e.g. after a restart) or admin buttons pressed by non-admins.
    await call.answer("⚠️ Bu tugma endi faol emas.", show_alert=True)
