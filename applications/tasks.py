import hashlib
import secrets
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from llm import get_llm
from llm.similarity import cosine_similarity

from .models import Application, ApplicationStatus
from .text_extraction import extract_resume_text


@shared_task
def parse_and_screen_resume(application_id):
    application = Application.objects.select_related("job_position", "candidate").get(
        id=application_id
    )
    job = application.job_position

    text = extract_resume_text(application.resume_file.path)
    application.extracted_text = text
    application.save(update_fields=["extracted_text"])

    llm = get_llm()
    resume_embedding = llm.embed(text)
    job_embedding = llm.embed(job.raw_jd_text)
    embedding_similarity = cosine_similarity(resume_embedding, job_embedding)

    analysis = llm.analyze_resume(text, job)
    skill_coverage_ratio = float(analysis.get("skill_coverage_ratio") or 0.0)

    match_score = round(
        (embedding_similarity * 100 * 0.6) + (skill_coverage_ratio * 100 * 0.4), 2
    )

    application.match_score = match_score
    application.gap_analysis = {
        "matched_skills": analysis.get("matched_skills", []),
        "missing_skills": analysis.get("missing_skills", []),
        "missing_context": analysis.get("missing_context", ""),
    }
    application.status = ApplicationStatus.SCREENING
    application.save(update_fields=["match_score", "gap_analysis", "status"])

    if match_score >= settings.MATCH_SCORE_THRESHOLD:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        application.tokens.create(
            token_hash=token_hash,
            expires_at=timezone.now() + timedelta(hours=48),
        )
        application.status = ApplicationStatus.SHORTLISTED
        application.save(update_fields=["status"])
        dispatch_invite_email.delay(str(application.id), raw_token)
    else:
        application.status = ApplicationStatus.REJECTED
        application.save(update_fields=["status"])
        dispatch_rejection_email.delay(str(application.id))


@shared_task
def dispatch_invite_email(application_id, token):
    application = Application.objects.select_related("candidate", "job_position").get(
        id=application_id
    )
    interview_url = f"{settings.FRONTEND_URL}/interview?token={token}"
    send_mail(
        subject=f"You're shortlisted for {application.job_position.title}!",
        message=(
            f"Hi {application.candidate.full_name},\n\n"
            f"Congratulations, your resume matched our criteria for {application.job_position.title}. "
            f"Start your AI interview here (link expires in 48 hours):\n{interview_url}\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[application.candidate.email],
    )


@shared_task
def dispatch_rejection_email(application_id):
    application = Application.objects.select_related("candidate", "job_position").get(
        id=application_id
    )
    send_mail(
        subject=f"Update on your application for {application.job_position.title}",
        message=(
            f"Hi {application.candidate.full_name},\n\n"
            f"Thank you for applying to {application.job_position.title}. "
            "We won't be moving forward with your application at this time."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[application.candidate.email],
    )
