# models.py (Django models)
from django.db import models

class TelegramUser(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=150, null=True, blank=True)
    first_name = models.CharField(max_length=150, null=True, blank=True)
    last_name = models.CharField(max_length=150, null=True, blank=True)
    language_code = models.CharField(max_length=10, null=True, blank=True)  # Shortened max_length for language code
    created_at = models.DateTimeField(auto_now_add=True)
    is_admin = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip() or self.username or str(self.telegram_id)

class Question(models.Model):
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField(null=True, blank=True)
    image_file_id = models.CharField(max_length=255, null=True, blank=True)
    document_file_id = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_answered = models.BooleanField(default=False)
    in_progress = models.BooleanField(default=False)

    def __str__(self):
        return self.text[:50] if self.text else "Savol (matnsiz)"

class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    responder = models.ForeignKey(TelegramUser, on_delete=models.SET_NULL, null=True, related_name='responses')
    content = models.JSONField(default=list)  # List of dicts: [{'type': 'text', 'text': 'content'}, {'type': 'photo', 'file_id': 'id', 'caption': 'cap'}, ...]
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.content:
            first_item = self.content[0]
            if first_item.get('type') == 'text':
                return first_item['text'][:50]
        return "Javob"