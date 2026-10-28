from django.contrib import admin

from .models import InterviewEvent, InterviewQA, InterviewRecording, InterviewSession, InterviewToken


@admin.register(InterviewToken)
class InterviewTokenAdmin(admin.ModelAdmin):
    list_display = ("application", "expires_at", "is_used", "created_at")


@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ("application", "started_at", "completed_at", "overall_score")


@admin.register(InterviewQA)
class InterviewQAAdmin(admin.ModelAdmin):
    list_display = ("session", "question_type", "evaluation_score", "created_at")


@admin.register(InterviewEvent)
class InterviewEventAdmin(admin.ModelAdmin):
    list_display = ("session", "event_type", "duration_ms", "created_at")
    list_filter = ("event_type",)


@admin.register(InterviewRecording)
class InterviewRecordingAdmin(admin.ModelAdmin):
    list_display = ("session", "qa", "content_type", "size_bytes", "updated_at")
