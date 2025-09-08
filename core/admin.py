from django.contrib import admin
from .models import TelegramUser, Question, Answer

@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'username', 'is_admin')

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'text', 'is_answered', 'created_at')
    list_filter = ('is_answered',)

@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('question', 'responder', 'created_at')
