import asyncio
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import QUESTION_TEXT_MAX_LENGTH, Answer, Question, TelegramUser
from core.services import (
    CLAIM_TTL,
    MAX_ANSWER_PARTS,
    ClaimResult,
    TelegramProfile,
    admin_chat_ids,
    claim_question,
    create_answer,
    create_question,
    is_admin,
    release_question,
    upsert_telegram_user,
    validate_answer_content,
    validate_question_text,
)
from tests.conftest import ADMIN_ID

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def student(make_user):
    return make_user(2000)


@pytest.fixture
def admins(make_user):
    return make_user(5001, is_admin=True), make_user(5002, is_admin=True)


@pytest.fixture
def question(student):
    return Question.objects.create(user=student, text="Integral nima?")


async def test_is_admin_from_env_and_db(admins):
    assert await is_admin(ADMIN_ID)  # from settings.TELEGRAM_ADMINS
    assert await is_admin(admins[0].telegram_id)  # from DB flag
    assert not await is_admin(999)


async def test_upsert_creates_updates_and_promotes_env_admins():
    user, created = await upsert_telegram_user(TelegramProfile(id=ADMIN_ID, username="old"))
    assert created and user.is_admin

    user, created = await upsert_telegram_user(TelegramProfile(id=ADMIN_ID, username="new"))
    assert not created
    assert user.username == "new"


async def test_upsert_never_demotes_db_admin(admins):
    user, _ = await upsert_telegram_user(TelegramProfile(id=admins[0].telegram_id))
    assert user.is_admin


async def test_admin_chat_ids_merges_env_and_db(admins):
    assert await admin_chat_ids() == sorted({ADMIN_ID, 5001, 5002})


def test_validate_question_text():
    assert validate_question_text("  salom  ") == "salom"
    with pytest.raises(ValidationError):
        validate_question_text("   ")
    with pytest.raises(ValidationError):
        validate_question_text("x" * (QUESTION_TEXT_MAX_LENGTH + 1))


async def test_create_question_validates_and_strips(student):
    q = await create_question(student, "  Savol  ", image_file_id="img", document_file_id="")
    assert q.text == "Savol"
    assert q.image_file_id == "img"
    assert q.document_file_id is None
    with pytest.raises(ValidationError):
        await create_question(student, "")


async def test_claim_is_exclusive(question, admins):
    first, second = admins
    assert await claim_question(question.pk, first) is ClaimResult.CLAIMED
    assert await claim_question(question.pk, second) is ClaimResult.LOCKED
    # The same admin may re-open their own claim.
    assert await claim_question(question.pk, first) is ClaimResult.CLAIMED


async def test_concurrent_claims_only_one_wins(question, admins):
    results = await asyncio.gather(*(claim_question(question.pk, admin) for admin in admins))
    assert sorted(r.value for r in results) == ["claimed", "locked"]


async def test_stale_claim_can_be_taken_over(question, admins):
    first, second = admins
    await claim_question(question.pk, first)
    await Question.objects.filter(pk=question.pk).aupdate(claimed_at=timezone.now() - CLAIM_TTL - timedelta(minutes=1))
    assert await claim_question(question.pk, second) is ClaimResult.CLAIMED


async def test_claim_missing_or_answered(question, admins):
    assert await claim_question(999_999, admins[0]) is ClaimResult.NOT_FOUND
    await Question.objects.filter(pk=question.pk).aupdate(is_answered=True)
    assert await claim_question(question.pk, admins[0]) is ClaimResult.ALREADY_ANSWERED


async def test_release_question(question, admins):
    await claim_question(question.pk, admins[0])
    await release_question(question.pk)
    q = await Question.objects.aget(pk=question.pk)
    assert (q.in_progress, q.claimed_by_id, q.claimed_at) == (False, None, None)


def test_create_answer_marks_question_answered(question, admins):
    question.in_progress = True
    question.claimed_by = admins[0]
    question.save()

    answer = create_answer(question, [{"type": "text", "text": "Javob"}], responder=admins[0])

    question.refresh_from_db()
    assert question.is_answered and not question.in_progress and question.claimed_by is None
    assert answer.delivery_status == Answer.DeliveryStatus.PENDING
    assert answer.responder == admins[0]


@pytest.mark.parametrize(
    "content",
    [
        [],
        [{"type": "sticker", "file_id": "x"}],
        [{"type": "text", "text": "  "}],
        [{"type": "text", "text": "x" * 5000}],
        [{"type": "photo"}],
        [{"type": "photo", "file_id": "f", "caption": "c" * 2000}],
        [{"type": "text", "text": "a"}] * (MAX_ANSWER_PARTS + 1),
    ],
)
def test_validate_answer_content_rejects(content):
    with pytest.raises(ValidationError):
        validate_answer_content(content)


def test_invalid_answer_is_not_saved(question):
    with pytest.raises(ValidationError):
        create_answer(question, [])
    question.refresh_from_db()
    assert not question.is_answered
    assert not Answer.objects.exists()


def test_telegram_profile_trims_language_code():
    class U:
        id, username, first_name, last_name, language_code = 1, "u", "f", None, "en-GB-oxendict"

    assert TelegramProfile.from_aiogram(U()).language_code == "en-GB-oxen"
    assert TelegramUser._meta.get_field("language_code").max_length == 10
