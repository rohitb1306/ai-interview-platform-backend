import uuid

from django.db import models


class ApplicationStatus(models.TextChoices):
    PENDING = "PENDING"
    SCREENING = "SCREENING"
    SHORTLISTED = "SHORTLISTED"
    REJECTED = "REJECTED"
    INTERVIEW_IN_PROGRESS = "INTERVIEW_IN_PROGRESS"
    COMPLETED = "COMPLETED"


class Application(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate = models.ForeignKey(
        "candidates.Candidate", on_delete=models.CASCADE, related_name="applications"
    )
    job_position = models.ForeignKey(
        "jobs.JobPosition", on_delete=models.PROTECT, related_name="applications"
    )
    resume_file = models.FileField(upload_to="resumes/%Y/%m/")
    extracted_text = models.TextField(blank=True, null=True)
    match_score = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    gap_analysis = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=30, choices=ApplicationStatus.choices, default=ApplicationStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.candidate.full_name} -> {self.job_position.title} ({self.status})"
