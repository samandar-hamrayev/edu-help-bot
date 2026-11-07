"""End-to-end handler tests: real Dispatcher, routers, filters and middlewares;
only the Telegram API is faked (see ``FakeBot``)."""

import pytest
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import AnswerCallbackQuery, EditMessageText, GetChatMember, SendMessage, SendPhoto
from aiogram.types import ChatMemberLeft, ChatMemberRestricted, PhotoSize, User

from core.models import QUESTION_TEXT_MAX_LENGTH, Answer, Question, TelegramUser
from tests.conftest import ADMIN_ID, OTHER_STUDENT_ID, STUDENT_ID

pytestmark = pytest.mark.django_db(transaction=True)


def last_text(bot, chat_id):
    texts = bot.texts(chat_id)
    return texts[-1] if texts else ""


def callback_alerts(bot):
    return [c.text for c in bot.sent(AnswerCallbackQuery) if c.text]


@pytest.fixture
def student(make_user):
    return make_user(STUDENT_ID)


@pytest.fixture
def admin_user(make_user):
    return make_user(ADMIN_ID, is_admin=True)


@pytest.fixture
def pending_question(student):
    return Question.objects.create(user=student, text="Limit nima?")


# ----------------------------------------------------------------------- /start


async def test_start_registers_user_and_notifies_admins(bot, send):
    await send(STUDENT_ID, "/start")

    user = await TelegramUser.objects.aget(telegram_id=STUDENT_ID)
    assert user.first_name == "Ali" and not user.is_admin
    assert "Xush kelibsiz" in bot.texts(STUDENT_ID)[0]
    assert "Yangi foydalanuvchi" in last_text(bot, ADMIN_ID)

    # Second /start: no duplicate user, no second admin notification.
    await send(STUDENT_ID, "/start")
    assert await TelegramUser.objects.acount() == 1
    assert len(bot.texts(ADMIN_ID)) == 1


async def test_start_promotes_env_admin(bot, send):
    await send(ADMIN_ID, "/start")
    assert (await TelegramUser.objects.aget(telegram_id=ADMIN_ID)).is_admin


async def test_help_differs_for_admins(bot, send, admin_user):
    await send(STUDENT_ID, "/help")
    await send(ADMIN_ID, "/help")
    assert "/pending_questions" not in last_text(bot, STUDENT_ID)
    assert "/pending_questions" in last_text(bot, ADMIN_ID)


# -------------------------------------------------------------- question flow


async def test_full_question_flow_creates_question_and_notifies_admins(bot, send):
    await send(STUDENT_ID, "/question")
    await send(STUDENT_ID, callback="skip_media")
    await send(STUDENT_ID, "Hosila <b>nima</b>?")
    assert "Yuborishni tasdiqlaysizmi" in last_text(bot, STUDENT_ID)
    # User text is HTML-escaped in the preview.
    assert "&lt;b&gt;" in last_text(bot, STUDENT_ID)

    await send(STUDENT_ID, callback="confirm_send")

    question = await Question.objects.aget()
    assert question.text == "Hosila <b>nima</b>?"
    assert "yuborildi" in last_text(bot, STUDENT_ID)
    admin_msg = bot.sent(SendMessage, ADMIN_ID)[-1]
    assert "&lt;b&gt;nima" in admin_msg.text
    assert admin_msg.reply_markup.inline_keyboard[0][0].callback_data == f"answer_q_{question.pk}"

    # A second tap on "confirm" (stale state) must not create a duplicate.
    await send(STUDENT_ID, callback="confirm_send")
    assert await Question.objects.acount() == 1


async def test_question_with_photo_sends_photo_to_admins(bot, send):
    photo = [
        PhotoSize(file_id="small", file_unique_id="s", width=1, height=1),
        PhotoSize(file_id="big", file_unique_id="b", width=9, height=9),
    ]
    await send(STUDENT_ID, "/question")
    await send(STUDENT_ID, callback="add_photo")
    await send(STUDENT_ID, None, photo=photo)
    await send(STUDENT_ID, "x" * 2000)
    await send(STUDENT_ID, callback="confirm_send")

    question = await Question.objects.aget()
    assert question.image_file_id == "big"
    sent_photo = bot.sent(SendPhoto, ADMIN_ID)[0]
    assert sent_photo.photo == "big"
    assert len(sent_photo.caption) <= 1024  # caption limit respected


async def test_question_text_too_long_is_rejected(bot, send):
    await send(STUDENT_ID, "/question")
    await send(STUDENT_ID, callback="skip_media")
    await send(STUDENT_ID, "x" * (QUESTION_TEXT_MAX_LENGTH + 1))
    assert "oshmasligi" in last_text(bot, STUDENT_ID)
    assert not await Question.objects.aexists()


async def test_wrong_media_type_gets_hint(bot, send):
    await send(STUDENT_ID, "/question")
    await send(STUDENT_ID, callback="add_photo")
    await send(STUDENT_ID, "not a photo")
    assert "rasm yuboring" in last_text(bot, STUDENT_ID)


async def test_cancel_question_flow(bot, send):
    await send(STUDENT_ID, "/question")
    await send(STUDENT_ID, callback="skip_media")
    await send(STUDENT_ID, "/cancel")
    assert "bekor qilindi" in last_text(bot, STUDENT_ID)
    await send(STUDENT_ID, "Bu savol emas")
    assert not await Question.objects.aexists()


async def test_admin_notification_failure_does_not_break_flow(bot, send, make_user):
    await TelegramUser.objects.acreate(telegram_id=7777, is_admin=True)

    def fail_for_blocked_admin(method):
        if method.chat_id == 7777:
            return TelegramForbiddenError(method, "Forbidden: bot was blocked by the user")
        return True

    bot.responses[SendMessage] = fail_for_blocked_admin
    await send(STUDENT_ID, "/question")
    await send(STUDENT_ID, callback="skip_media")
    await send(STUDENT_ID, "Savol")
    await send(STUDENT_ID, callback="confirm_send")

    assert await Question.objects.acount() == 1
    assert "yuborildi" in last_text(bot, STUDENT_ID)


# --------------------------------------------------------------- my questions


async def test_my_questions_lists_only_own_questions(bot, send, student, make_user):
    await Question.objects.acreate(user=student, text="Mening savolim")
    await Question.objects.acreate(user=await TelegramUser.objects.acreate(telegram_id=OTHER_STUDENT_ID), text="Begona")

    await send(STUDENT_ID, "/my_questions")
    markup = bot.sent(SendMessage, STUDENT_ID)[-1].reply_markup
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert len(labels) == 1 and "Mening savolim" in labels[0]


async def test_my_questions_empty(bot, send):
    await send(STUDENT_ID, "/my_questions")
    assert "hech qanday savol" in last_text(bot, STUDENT_ID)


async def test_cannot_view_someone_elses_question(bot, send, pending_question):
    await send(OTHER_STUDENT_ID, callback=f"qdetail_{pending_question.pk}")
    assert "topilmadi" in callback_alerts(bot)[-1]
    assert not bot.sent(SendMessage, OTHER_STUDENT_ID)


async def test_question_detail_shows_answers(bot, send, pending_question):
    await Answer.objects.acreate(question=pending_question, content=[{"type": "text", "text": "Javob matni"}])
    await send(STUDENT_ID, callback=f"qdetail_{pending_question.pk}")
    assert bot.texts(STUDENT_ID)[-1] == "Javob matni"


async def test_my_questions_pagination(bot, send, student):
    await Question.objects.abulk_create([Question(user=student, text=f"Q{i}") for i in range(12)])
    await send(STUDENT_ID, callback="qnav_2")
    edit = bot.sent(EditMessageText)[-1]
    labels = [b.text for row in edit.reply_markup.inline_keyboard for b in row]
    assert "⬅️ Oldingi" in labels
    assert len([label for label in labels if label.startswith("⏳")]) == 2


async def test_malformed_callback_data_is_handled(bot, send):
    await send(STUDENT_ID, callback="qdetail_abc")
    assert "topilmadi" in callback_alerts(bot)[-1]


# --------------------------------------------------------------- admin guards


@pytest.mark.parametrize("command", ["/stats", "/pending_questions"])
async def test_admin_commands_denied_for_students(bot, send, command):
    await send(STUDENT_ID, command)
    assert "faqat adminlar" in last_text(bot, STUDENT_ID)


async def test_student_cannot_answer_by_forging_callback(bot, send, pending_question):
    await send(STUDENT_ID, callback=f"answer_q_{pending_question.pk}")

    await pending_question.arefresh_from_db()
    assert not pending_question.in_progress
    assert "faol emas" in callback_alerts(bot)[-1]
    # Further text from the student is not collected as an answer.
    await send(STUDENT_ID, "fake answer")
    assert not await Answer.objects.aexists()


async def test_student_cannot_browse_pending_questions(bot, send, pending_question):
    await send(STUDENT_ID, callback=f"view_pending_q_{pending_question.pk}")
    assert not bot.texts(STUDENT_ID)


async def test_stats_for_admin(bot, send, admin_user, pending_question):
    await Answer.objects.acreate(question=pending_question, content=[{"type": "text", "text": "a"}])
    await Question.objects.filter(pk=pending_question.pk).aupdate(is_answered=True)
    await send(ADMIN_ID, "/stats")
    text = last_text(bot, ADMIN_ID)
    assert "Bot statistikasi" in text
    assert "Javob berilgan: <code>1</code>" in text


async def test_pending_questions_for_admin(bot, send, admin_user, pending_question):
    await send(ADMIN_ID, "/pending_questions")
    markup = bot.sent(SendMessage, ADMIN_ID)[-1].reply_markup
    assert markup.inline_keyboard[0][0].callback_data == f"view_pending_q_{pending_question.pk}"

    await send(ADMIN_ID, callback=f"view_pending_q_{pending_question.pk}")
    detail = bot.sent(SendMessage, ADMIN_ID)[-1]
    assert "Limit nima?" in detail.text
    assert detail.reply_markup.inline_keyboard[0][0].callback_data == f"answer_q_{pending_question.pk}"


# ---------------------------------------------------------- admin answer flow


async def test_admin_answers_and_student_is_notified(bot, send, admin_user, pending_question):
    await send(ADMIN_ID, callback=f"answer_q_{pending_question.pk}")
    await pending_question.arefresh_from_db()
    assert pending_question.in_progress

    await send(ADMIN_ID, "Limit — bu chegaraviy qiymat")
    await send(ADMIN_ID, None, photo=[PhotoSize(file_id="graph", file_unique_id="g", width=1, height=1)])
    await send(ADMIN_ID, callback="send_answer")

    answer = await Answer.objects.aget()
    assert answer.delivery_status == Answer.DeliveryStatus.DELIVERED
    assert [p["type"] for p in answer.content] == ["text", "photo"]
    assert bot.texts(STUDENT_ID)[-1] == "Limit — bu chegaraviy qiymat"
    assert bot.sent(SendPhoto, STUDENT_ID)[0].photo == "graph"
    assert "yuborildi" in last_text(bot, ADMIN_ID)

    await pending_question.arefresh_from_db()
    assert pending_question.is_answered and not pending_question.in_progress


async def test_answer_to_blocked_user_is_saved_and_reported(bot, send, admin_user, pending_question):
    def blocked(method):
        if method.chat_id == STUDENT_ID:
            return TelegramForbiddenError(method, "Forbidden: bot was blocked by the user")
        return True

    bot.responses[SendMessage] = blocked
    await send(ADMIN_ID, callback=f"answer_q_{pending_question.pk}")
    await send(ADMIN_ID, "Javob")
    await send(ADMIN_ID, callback="send_answer")

    answer = await Answer.objects.aget()
    assert answer.delivery_status == Answer.DeliveryStatus.FAILED
    assert "yetkazib bo'lmadi" in last_text(bot, ADMIN_ID)


async def test_second_admin_cannot_take_claimed_question(bot, send, admin_user, pending_question):
    await TelegramUser.objects.acreate(telegram_id=1001, is_admin=True)
    await send(ADMIN_ID, callback=f"answer_q_{pending_question.pk}")
    await send(1001, callback=f"answer_q_{pending_question.pk}")
    assert "boshqa admin" in callback_alerts(bot)[-1]


async def test_send_without_parts_is_rejected(bot, send, admin_user, pending_question):
    await send(ADMIN_ID, callback=f"answer_q_{pending_question.pk}")
    await send(ADMIN_ID, callback="send_answer")
    assert "qo'shilmagan" in callback_alerts(bot)[-1]
    assert not await Answer.objects.aexists()


@pytest.mark.parametrize("how", ["button", "command"])
async def test_cancel_answer_releases_claim(bot, send, admin_user, pending_question, how):
    await send(ADMIN_ID, callback=f"answer_q_{pending_question.pk}")
    if how == "button":
        await send(ADMIN_ID, callback="cancel_answer")
    else:
        await send(ADMIN_ID, "/cancel")
    await pending_question.arefresh_from_db()
    assert not pending_question.in_progress and pending_question.claimed_by_id is None


async def test_answer_part_too_long_is_rejected(bot, send, admin_user, pending_question):
    await send(ADMIN_ID, callback=f"answer_q_{pending_question.pk}")
    await send(ADMIN_ID, "x" * 4001)
    assert "oshmasligi" in last_text(bot, ADMIN_ID)


# --------------------------------------------------------------- membership


@pytest.fixture
def required_chat(settings):
    settings.REQUIRED_CHATS = [(-100123, "@edu_channel")]


async def test_non_member_is_blocked(bot, send, required_chat):
    bot.responses[GetChatMember] = ChatMemberLeft(user=User(id=STUDENT_ID, is_bot=False, first_name="A"))
    await send(STUDENT_ID, "/my_questions")

    msg = bot.sent(SendMessage, STUDENT_ID)[-1]
    assert "A'zolik talabi" in msg.text
    assert msg.reply_markup.inline_keyboard[0][0].url == "https://t.me/edu_channel"


async def test_public_commands_skip_membership(bot, send, required_chat):
    bot.responses[GetChatMember] = ChatMemberLeft(user=User(id=STUDENT_ID, is_bot=False, first_name="A"))
    await send(STUDENT_ID, "/start")
    assert not bot.sent(GetChatMember)


async def test_member_passes_and_result_is_cached(bot, send, required_chat):
    await send(STUDENT_ID, "/my_questions")
    await send(STUDENT_ID, "/my_questions")
    assert "hech qanday savol" in last_text(bot, STUDENT_ID)
    assert len(bot.sent(GetChatMember)) == 1


async def test_restricted_but_member_counts_as_member(bot, send, required_chat):
    bot.responses[GetChatMember] = lambda m: ChatMemberRestricted.model_construct(
        status=ChatMemberStatus.RESTRICTED, is_member=True
    )
    await send(STUDENT_ID, "/my_questions")
    assert "hech qanday savol" in last_text(bot, STUDENT_ID)


async def test_membership_api_error_fails_closed(bot, send, required_chat):
    bot.responses[GetChatMember] = lambda m: TelegramBadRequest(m, "Bad Request: member list is inaccessible")
    await send(STUDENT_ID, "/my_questions")
    assert "A'zolik talabi" in last_text(bot, STUDENT_ID)


async def test_admins_skip_membership(bot, send, required_chat):
    await send(ADMIN_ID, "/my_questions")
    assert not bot.sent(GetChatMember)


async def test_check_membership_button(bot, send, required_chat):
    bot.responses[GetChatMember] = ChatMemberLeft(user=User(id=STUDENT_ID, is_bot=False, first_name="A"))
    await send(STUDENT_ID, callback="check_membership")
    assert "A'zolik talabi" in bot.sent(EditMessageText)[-1].text

    bot.responses.pop(GetChatMember)
    await send(STUDENT_ID, callback="check_membership")
    assert "tasdiqlandi" in bot.sent(EditMessageText)[-1].text
