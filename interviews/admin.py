from django.contrib import admin

from .models import InterviewQA, InterviewSession, InterviewToken


@admin.register(InterviewToken)
class InterviewTokenAdmin(admin.ModelAdmin):
    list_display = ("application", "expires_at", "is_used", "created_at")


@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ("application", "started_at", "completed_at", "overall_score")


@admin.register(InterviewQA)
class InterviewQAAdmin(admin.ModelAdmin):
    list_display = ("session", "question_type", "evaluation_score", "created_at")
