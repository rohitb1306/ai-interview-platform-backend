from django.contrib import admin

from .models import Application


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("candidate", "job_position", "status", "match_score", "created_at")
    list_filter = ("status", "job_position")
    search_fields = ("candidate__full_name", "candidate__email")
