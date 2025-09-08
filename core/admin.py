from django.contrib import admin
from .models import TelegramUser, Question, Answer
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from django.contrib.auth.models import User, Group

@admin.register(TelegramUser)
class TelegramUserAdmin(UnfoldModelAdmin):
    list_display = ('telegram_id', 'username', 'is_admin')

@admin.register(Question)
class QuestionAdmin(UnfoldModelAdmin):
    list_display = ('id', 'user', 'text', 'is_answered', 'created_at')
    list_filter = ('is_answered',)

@admin.register(Answer)
class AnswerAdmin(UnfoldModelAdmin):
    list_display = ('question', 'responder', 'created_at')

admin.site.unregister(Group)