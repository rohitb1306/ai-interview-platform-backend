import uuid

from django.db import models


class QuestionType(models.TextChoices):
    TECHNICAL = "TECHNICAL"
    BEHAVIORAL = "BEHAVIORAL"
    SYSTEM_DESIGN = "SYSTEM_DESIGN"


class InterviewToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="tokens"
    )
    token_hash = models.CharField(max_length=255, unique=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Token for {self.application_id}"


class InterviewSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="sessions"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    overall_score = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    final_feedback = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Session {self.id} for {self.application_id}"


class InterviewQA(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        InterviewSession, on_delete=models.CASCADE, related_name="qa_pairs"
    )
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    candidate_answer_text = models.TextField(blank=True, null=True)
    evaluation_score = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    ai_feedback = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"QA {self.id} ({self.question_type})"
