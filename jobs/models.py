import uuid

from django.db import models


class JobPosition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=100)
    department = models.CharField(max_length=50, blank=True)
    raw_jd_text = models.TextField()
    required_skills = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
