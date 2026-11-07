import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from core.models import Answer, Question

pytestmark = pytest.mark.django_db


@pytest.fixture
def question(make_user):
    return Question.objects.create(user=make_user(2000), text="Savol", in_progress=True)


@pytest.fixture
def staff_client(client):
    user = User.objects.create_superuser("admin", "admin@example.com", "pass-12345")
    client.force_login(user)
    client.user = user
    return client


def test_healthz(client):
    # Served before host validation, so an internal Host header is fine.
    response = client.get("/healthz/", HTTP_HOST="10.0.0.5:8000")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_admin(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response["Location"] == "/admin/"


def test_admin_requires_login(client):
    response = client.get(reverse("admin:core_question_changelist"))
    assert response.status_code == 302


@pytest.mark.parametrize("name", ["core_question", "core_answer", "core_telegramuser"])
def test_admin_changelists_render(staff_client, question, name):
    assert staff_client.get(reverse(f"admin:{name}_changelist")).status_code == 200


def test_question_detail_has_answer_link(staff_client, question):
    response = staff_client.get(reverse("admin:core_question_change", args=[question.pk]))
    assert response.status_code == 200
    assert f"?question={question.pk}" in response.content.decode()


def test_answer_from_admin_is_queued_for_delivery(staff_client, question):
    response = staff_client.post(
        reverse("admin:core_answer_add"), {"question": question.pk, "reply_text": "  Mana javob  "}
    )
    assert response.status_code == 302, response.content.decode()[:2000]

    answer = Answer.objects.get()
    assert answer.content == [{"type": "text", "text": "Mana javob"}]
    assert answer.staff_user == staff_client.user
    assert answer.delivery_status == Answer.DeliveryStatus.PENDING
    question.refresh_from_db()
    assert question.is_answered and not question.in_progress


def test_answer_from_admin_rejects_blank_text(staff_client, question):
    response = staff_client.post(reverse("admin:core_answer_add"), {"question": question.pk, "reply_text": "   "})
    assert response.status_code == 200
    assert not Answer.objects.exists()


def test_retry_delivery_action(staff_client, question):
    failed = Answer.objects.create(
        question=question,
        content=[{"type": "text", "text": "x"}],
        delivery_status=Answer.DeliveryStatus.FAILED,
        delivery_attempts=5,
        delivery_error="blocked",
    )
    response = staff_client.post(
        reverse("admin:core_answer_changelist"),
        {"action": "retry_delivery", "_selected_action": [failed.pk]},
    )
    assert response.status_code == 302
    failed.refresh_from_db()
    assert failed.delivery_status == Answer.DeliveryStatus.PENDING
    assert failed.delivery_attempts == 0


def test_release_lock_action(staff_client, question):
    staff_client.post(
        reverse("admin:core_question_changelist"),
        {"action": "release_lock", "_selected_action": [question.pk]},
    )
    question.refresh_from_db()
    assert not question.in_progress


def test_healthz_reports_database_outage(client, monkeypatch):
    from core import views

    class BrokenConnection:
        def cursor(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(views, "connection", BrokenConnection())
    response = client.get("/healthz/")
    assert response.status_code == 503
