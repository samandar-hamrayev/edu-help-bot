from django.db import models

class TelegramUser(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=150, null=True, blank=True)
    first_name = models.CharField(max_length=150, null=True, blank=True)
    last_name = models.CharField(max_length=150, null=True, blank=True)
    language_code = models.CharField(max_length=150, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_admin = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class Question(models.Model):
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE)
    text = models.TextField(null=True, blank=True)
    image_file_id = models.CharField(max_length=255, null=True, blank=True)
    document_file_id = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_answered = models.BooleanField(default=False)
    in_progress = models.BooleanField(default=False)

    def __str__(self):
        return self.text

class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    responder = models.ForeignKey(TelegramUser, on_delete=models.SET_NULL, null=True)
    text = models.TextField(null=True, blank=True)
    image_file_id = models.CharField(max_length=255, null=True, blank=True)
    document_file_id = models.CharField(max_length=255, null=True, blank=True)
    voice_file_id = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.text
