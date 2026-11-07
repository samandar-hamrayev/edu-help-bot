import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError
from aiogram.methods import SendMessage, SendPhoto

from bot import delivery
from bot.delivery import ANSWER_HEADER, deliver_answer, deliver_pending_answers, reset_stuck_answers
from core.models import Answer, Question
from core.services import create_answer
from tests.conftest import STUDENT_ID

pytestmark = pytest.mark.django_db(transaction=True)

Status = Answer.DeliveryStatus


@pytest.fixture
def answer(make_user):
    question = Question.objects.create(user=make_user(STUDENT_ID), text="Q?")
    return create_answer(
        question,
        [{"type": "text", "text": "a < b & c"}, {"type": "photo", "file_id": "photo-id", "caption": "rasm"}],
    )


async def test_deliver_answer_sends_all_parts(bot, answer):
    assert await deliver_answer(bot, answer.pk) is True

    assert bot.texts(STUDENT_ID) == [ANSWER_HEADER, "a < b & c"]
    # User/admin text is sent without HTML parsing so "<" can't break the message.
    assert bot.sent(SendMessage, STUDENT_ID)[1].parse_mode is None
    assert bot.sent(SendPhoto, STUDENT_ID)[0].photo == "photo-id"

    await answer.arefresh_from_db()
    assert answer.delivery_status == Status.DELIVERED
    assert answer.delivered_at is not None
    assert answer.delivery_attempts == 1


async def test_deliver_answer_is_idempotent(bot, answer):
    assert await deliver_answer(bot, answer.pk)
    assert not await deliver_answer(bot, answer.pk)
    assert len(bot.sent(SendMessage)) == 2


async def test_blocked_user_marks_failed_without_retry(bot, answer):
    bot.responses[SendMessage] = lambda m: TelegramForbiddenError(m, "Forbidden: bot was blocked by the user")

    assert await deliver_answer(bot, answer.pk) is False

    await answer.arefresh_from_db()
    assert answer.delivery_status == Status.FAILED
    assert "blocked" in answer.delivery_error
    # Failed answers are not picked up again by the outbox.
    assert await deliver_pending_answers(bot) == 0


async def test_network_error_is_retried_then_gives_up(bot, answer, monkeypatch):
    monkeypatch.setattr(delivery, "MAX_ATTEMPTS", 2)
    bot.responses[SendMessage] = lambda m: TelegramNetworkError(m, "timeout")

    assert await deliver_answer(bot, answer.pk) is False
    await answer.arefresh_from_db()
    assert answer.delivery_status == Status.PENDING

    assert await deliver_answer(bot, answer.pk) is False
    await answer.arefresh_from_db()
    assert answer.delivery_status == Status.FAILED
    assert answer.delivery_attempts == 2


async def test_unexpected_error_requeues_and_raises(bot, answer):
    bot.responses[SendMessage] = lambda m: RuntimeError("boom")
    with pytest.raises(RuntimeError):
        await deliver_answer(bot, answer.pk)
    await answer.arefresh_from_db()
    assert answer.delivery_status == Status.PENDING


async def test_outbox_delivers_admin_panel_answers(bot, answer):
    assert await deliver_pending_answers(bot) == 1
    await answer.arefresh_from_db()
    assert answer.delivery_status == Status.DELIVERED


async def test_reset_stuck_answers(answer):
    await Answer.objects.filter(pk=answer.pk).aupdate(delivery_status=Status.SENDING)
    assert await reset_stuck_answers() == 1
    await answer.arefresh_from_db()
    assert answer.delivery_status == Status.PENDING


async def test_send_content_supports_all_part_types(bot):
    from aiogram.methods import SendDocument, SendVideo, SendVoice

    from bot.utils.telegram import send_content

    await send_content(
        bot,
        1,
        [
            {"type": "video", "file_id": "v", "caption": "c"},
            {"type": "voice", "file_id": "o"},
            {"type": "document", "file_id": "d"},
            {"type": "sticker", "file_id": "ignored"},
        ],
    )
    assert [type(c) for c in bot.calls] == [SendVideo, SendVoice, SendDocument]


async def test_run_outbox_delivers_and_survives_errors(bot, answer, monkeypatch):
    import asyncio

    calls = 0
    real = delivery.deliver_pending_answers

    async def flaky(b):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("db hiccup")
        return await real(b)

    monkeypatch.setattr(delivery, "deliver_pending_answers", flaky)
    task = asyncio.create_task(delivery.run_outbox(bot, interval=0.01))
    for _ in range(200):
        await asyncio.sleep(0.01)
        await answer.arefresh_from_db()
        if answer.delivery_status == Status.DELIVERED:
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert answer.delivery_status == Status.DELIVERED
    assert calls >= 2


def test_bot_healthcheck(tmp_path, monkeypatch, settings):
    import os
    import time

    from bot import healthcheck

    beat = tmp_path / "beat"
    monkeypatch.setattr(healthcheck, "HEARTBEAT_FILE", str(beat))
    assert healthcheck.main() == 1  # missing

    settings.BOT_HEARTBEAT_FILE = str(beat)
    delivery.touch_heartbeat()
    assert healthcheck.main() == 0

    old = time.time() - 1000
    os.utime(beat, (old, old))
    assert healthcheck.main() == 1
