import pytest

from core.models import Answer, Question, TelegramUser

pytestmark = pytest.mark.django_db


def test_telegram_user_str_prefers_full_name():
    assert str(TelegramUser(telegram_id=1, first_name="Ali", last_name="Valiyev")) == "Ali Valiyev"
    assert str(TelegramUser(telegram_id=1, username="ali")) == "ali"
    assert str(TelegramUser(telegram_id=42)) == "42"


def test_question_defaults_and_str(make_user):
    question = Question.objects.create(user=make_user(1), text="x" * 80)
    assert question.is_answered is False
    assert question.in_progress is False
    assert str(question) == "x" * 50
    assert str(Question(text=None)) == "Savol (matnsiz)"


def test_answer_defaults_to_pending_delivery(make_user):
    question = Question.objects.create(user=make_user(1), text="Q")
    answer = Answer.objects.create(question=question, content=[{"type": "photo", "file_id": "f"}])
    assert answer.delivery_status == Answer.DeliveryStatus.PENDING
    assert answer.delivery_attempts == 0
    assert str(answer) == "Javob"
    answer.content = [{"type": "text", "text": "Hello"}]
    assert str(answer) == "Hello"
