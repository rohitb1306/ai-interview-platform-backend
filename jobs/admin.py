from django.contrib import admin

from .models import JobPosition


@admin.register(JobPosition)
class JobPositionAdmin(admin.ModelAdmin):
    list_display = ("title", "department", "created_at")
    search_fields = ("title", "department")
