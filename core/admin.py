from django import forms
from django.contrib import admin, messages
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import ANSWER_TEXT_MAX_LENGTH, Answer, Question, TelegramUser
from .services import save_answer


@admin.register(TelegramUser)
class TelegramUserAdmin(ModelAdmin):
    list_display = ("telegram_id", "username", "first_name", "is_admin", "created_at")
    list_filter = ("is_admin",)
    search_fields = ("telegram_id", "username", "first_name", "last_name")
    readonly_fields = ("telegram_id", "created_at")


class AnswerInline(TabularInline):
    model = Answer
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ("created_at", "author", "preview", "delivery_status", "delivered_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @display(description="Author")
    def author(self, obj: Answer) -> str:
        return str(obj.staff_user or obj.responder or "-")

    @display(description="Answer")
    def preview(self, obj: Answer) -> str:
        return str(obj)


@admin.register(Question)
class QuestionAdmin(ModelAdmin):
    list_display = ("id", "user", "short_text", "has_media", "is_answered", "in_progress", "created_at")
    list_filter = ("is_answered", "in_progress", "created_at")
    search_fields = ("text", "user__username", "user__first_name", "user__telegram_id")
    list_select_related = ("user",)
    readonly_fields = (
        "user",
        "text",
        "image_file_id",
        "document_file_id",
        "created_at",
        "is_answered",
        "in_progress",
        "claimed_by",
        "claimed_at",
        "answer_link",
    )
    fields = readonly_fields
    inlines = (AnswerInline,)
    actions = ("release_lock",)

    def has_add_permission(self, request):
        # Questions are created by students through the bot.
        return False

    @display(description="Text")
    def short_text(self, obj: Question) -> str:
        return str(obj)

    @display(description="Media", boolean=True)
    def has_media(self, obj: Question) -> bool:
        return bool(obj.image_file_id or obj.document_file_id)

    @display(description="Reply")
    def answer_link(self, obj: Question) -> str:
        url = reverse("admin:core_answer_add") + f"?question={obj.pk}"
        return format_html('<a class="font-semibold text-primary-600" href="{}">Write an answer →</a>', url)

    @admin.action(description="Release the 'in progress' lock")
    def release_lock(self, request, queryset):
        count = queryset.filter(is_answered=False).update(in_progress=False, claimed_by=None, claimed_at=None)
        self.message_user(request, f"Released {count} question(s).", messages.SUCCESS)


class AnswerAddForm(forms.ModelForm):
    reply_text = forms.CharField(
        label="Answer",
        widget=forms.Textarea(attrs={"rows": 8}),
        max_length=ANSWER_TEXT_MAX_LENGTH,
        help_text="Sent to the student as a Telegram message by the bot worker.",
    )

    class Meta:
        model = Answer
        fields = ("question",)

    def clean_reply_text(self) -> str:
        text = self.cleaned_data["reply_text"].strip()
        if not text:
            raise ValidationError("Answer text must not be empty.")
        return text


@admin.register(Answer)
class AnswerAdmin(ModelAdmin):
    list_display = ("id", "question", "author", "delivery_status", "delivery_attempts", "delivered_at", "created_at")
    list_filter = ("delivery_status", "created_at")
    search_fields = ("question__text", "question__user__username")
    list_select_related = ("question", "responder", "staff_user")
    autocomplete_fields = ("question",)
    actions = ("retry_delivery",)
    readonly_fields = (
        "question",
        "responder",
        "staff_user",
        "content",
        "created_at",
        "delivery_status",
        "delivery_attempts",
        "delivery_error",
        "delivered_at",
    )

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = AnswerAddForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        return ("question", "reply_text") if obj is None else self.readonly_fields

    def get_readonly_fields(self, request, obj=None):
        return () if obj is None else self.readonly_fields

    def has_change_permission(self, request, obj=None):
        # Answers are immutable once written (they may already be delivered);
        # the change page is view-only.
        return False

    def save_model(self, request, obj: Answer, form, change):
        if change:  # pragma: no cover - change is disabled above
            return
        obj.content = [{"type": "text", "text": form.cleaned_data["reply_text"]}]
        obj.staff_user = request.user
        save_answer(obj)
        self.message_user(
            request, "Answer saved. The bot will deliver it to the student within a few seconds.", messages.INFO
        )

    @display(description="Author")
    def author(self, obj: Answer) -> str:
        return str(obj.staff_user or obj.responder or "-")

    @admin.action(description="Retry delivery of failed answers")
    def retry_delivery(self, request, queryset):
        count = queryset.filter(delivery_status=Answer.DeliveryStatus.FAILED).update(
            delivery_status=Answer.DeliveryStatus.PENDING, delivery_attempts=0, delivery_error=""
        )
        self.message_user(request, f"Re-queued {count} answer(s) for delivery.", messages.SUCCESS)


admin.site.unregister(Group)
