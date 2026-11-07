from django.conf import settings
from django.db import models

QUESTION_TEXT_MAX_LENGTH = 3000
ANSWER_TEXT_MAX_LENGTH = 4000


class TelegramUser(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=150, null=True, blank=True)
    first_name = models.CharField(max_length=150, null=True, blank=True)
    last_name = models.CharField(max_length=150, null=True, blank=True)
    language_code = models.CharField(max_length=10, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_admin = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Telegram user"

    def __str__(self) -> str:
        full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return full_name or self.username or str(self.telegram_id)


class Question(models.Model):
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField(null=True, blank=True)
    image_file_id = models.CharField(max_length=255, null=True, blank=True)
    document_file_id = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_answered = models.BooleanField(default=False)
    # "Claim" lock so two admins don't answer the same question at once.
    in_progress = models.BooleanField(default=False)
    claimed_by = models.ForeignKey(
        TelegramUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_questions",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["is_answered", "-created_at"], name="question_pending_idx")]

    def __str__(self) -> str:
        return self.text[:50] if self.text else "Savol (matnsiz)"


class Answer(models.Model):
    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    # Telegram admin who answered from the bot (null when answered from the web admin).
    responder = models.ForeignKey(
        TelegramUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="responses"
    )
    # Django staff user who answered from the admin panel.
    staff_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="answers"
    )
    # Ordered parts: [{"type": "text", "text": "..."}, {"type": "photo", "file_id": "...", "caption": "..."}]
    content = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    delivery_status = models.CharField(
        max_length=16, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING, db_index=True
    )
    delivery_attempts = models.PositiveSmallIntegerField(default=0)
    delivery_error = models.CharField(max_length=500, blank=True, default="")
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:
        for item in self.content or []:
            if item.get("type") == "text" and item.get("text"):
                return item["text"][:50]
        return "Javob"
