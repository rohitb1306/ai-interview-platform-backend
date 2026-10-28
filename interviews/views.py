import hashlib
import logging

from django.core.files.base import ContentFile
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from applications.models import ApplicationStatus
from llm import get_llm

from .models import (
    InterviewEvent,
    InterviewQA,
    InterviewRecording,
    InterviewSession,
    InterviewToken,
)
from .serializers import (
    MAX_RECORDING_BYTES,
    TOTAL_QUESTIONS,
    InterviewEventCreateSerializer,
    InterviewStartSerializer,
    RecordingChunkSerializer,
    SubmitAnswerSerializer,
    TokenValidateResponseSerializer,
)

logger = logging.getLogger(__name__)

RECORDING_EXTENSIONS = {
    "video/webm": "webm",
    "video/mp4": "mp4",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
}


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _valid_token_queryset():
    return InterviewToken.objects.filter(is_used=False, expires_at__gt=timezone.now())


class ValidateTokenView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        raw_token = request.query_params.get("token", "")
        token = (
            _valid_token_queryset()
            .select_related("application__candidate", "application__job_position")
            .filter(token_hash=_hash_token(raw_token))
            .first()
        )
        if not token:
            return Response({"valid": False}, status=status.HTTP_400_BAD_REQUEST)

        open_session = (
            token.application.sessions.filter(completed_at__isnull=True)
            .order_by("-started_at")
            .first()
        )
        answered_count = (
            open_session.qa_pairs.filter(candidate_answer_text__isnull=False).count()
            if open_session
            else 0
        )
        data = TokenValidateResponseSerializer(
            {
                "valid": True,
                "candidate_name": token.application.candidate.full_name,
                "job_title": token.application.job_position.title,
                "in_progress": open_session is not None,
                "answered_count": answered_count,
                "total_questions": TOTAL_QUESTIONS,
            }
        ).data
        return Response(data, status=status.HTTP_200_OK)


def _question_payload(qa, number):
    return {"id": qa.id, "text": qa.question_text, "number": number, "total": TOTAL_QUESTIONS}


def _current_question(session):
    """Return (qa, number) for where the candidate is, generating the next question if needed.

    Returns None once all questions are answered. Raises if question generation fails;
    progress is already saved, so the caller can simply retry.
    """
    qa_pairs = list(session.qa_pairs.all())
    answered = [qa for qa in qa_pairs if qa.candidate_answer_text is not None]
    pending = next((qa for qa in qa_pairs if qa.candidate_answer_text is None), None)
    if pending:
        return pending, len(answered) + 1
    if len(answered) >= TOTAL_QUESTIONS:
        return None

    application = session.application
    question_data = get_llm().generate_question(
        job=application.job_position,
        application=application,
        previous_qa=answered,
        question_number=len(answered) + 1,
    )
    qa = InterviewQA.objects.create(
        session=session,
        question_text=question_data["text"],
        question_type=question_data["question_type"],
    )
    return qa, len(answered) + 1


def _complete_session(session):
    answered = [qa for qa in session.qa_pairs.all() if qa.candidate_answer_text is not None]
    scores = [qa.evaluation_score for qa in answered if qa.evaluation_score is not None]
    final_feedback = get_llm().generate_final_feedback(answered)

    with transaction.atomic():
        session.overall_score = round(sum(scores) / len(scores), 2) if scores else None
        session.final_feedback = final_feedback
        session.completed_at = timezone.now()
        session.save(update_fields=["overall_score", "final_feedback", "completed_at"])

        application = session.application
        application.status = ApplicationStatus.COMPLETED
        application.save(update_fields=["status"])
        # The link stays reusable for resuming until the interview is finished.
        application.tokens.filter(is_used=False).update(is_used=True)


def _ai_unavailable(message):
    return Response({"message": message}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class StartInterviewView(APIView):
    """Start the interview, or resume it from where the candidate left off."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = InterviewStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_token = serializer.validated_data["token"]

        with transaction.atomic():
            token = (
                _valid_token_queryset()
                .select_related("application__job_position")
                .select_for_update()
                .filter(token_hash=_hash_token(raw_token))
                .first()
            )
            if not token:
                return Response(
                    {"valid": False, "message": "Invalid or expired token."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            application = token.application
            session = (
                application.sessions.filter(completed_at__isnull=True)
                .order_by("-started_at")
                .first()
            )
            if session is None:
                session = InterviewSession.objects.create(
                    application=application, started_at=timezone.now()
                )
            application.status = ApplicationStatus.INTERVIEW_IN_PROGRESS
            application.save(update_fields=["status"])

        try:
            current = _current_question(session)
            if current is None:
                # Every answer is in but finalising failed earlier; finish now.
                _complete_session(session)
        except Exception:
            logger.exception("AI call failed while starting session %s", session.id)
            return _ai_unavailable("Could not load your interview right now. Please try again.")

        if current is None:
            return Response(
                {"session_id": session.id, "question": None, "is_complete": True},
                status=status.HTTP_200_OK,
            )
        qa, number = current
        return Response(
            {
                "session_id": session.id,
                "question": _question_payload(qa, number),
                "is_complete": False,
            },
            status=status.HTTP_200_OK,
        )


class SubmitAnswerView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SubmitAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        qa = get_object_or_404(
            InterviewQA.objects.select_related("session__application__job_position"),
            id=data["question_id"],
            session_id=data["session_id"],
        )
        session = qa.session
        if session.completed_at:
            return Response({"next_question": None, "is_complete": True}, status=status.HTTP_200_OK)

        try:
            # A retry after a failed next step skips re-grading an answer already saved.
            if qa.candidate_answer_text is None:
                evaluation = get_llm().evaluate_answer(qa.question_text, data["answer_text"])
                qa.candidate_answer_text = data["answer_text"]
                qa.evaluation_score = evaluation.get("score")
                qa.ai_feedback = evaluation.get("feedback", "")
                qa.save(
                    update_fields=["candidate_answer_text", "evaluation_score", "ai_feedback"]
                )

            current = _current_question(session)
            if current is None:
                _complete_session(session)
        except Exception:
            logger.exception("AI call failed while submitting answer in session %s", session.id)
            return _ai_unavailable(
                "Something went wrong on our side. Your progress is saved, please try again."
            )

        if current is None:
            return Response({"next_question": None, "is_complete": True}, status=status.HTTP_200_OK)
        next_qa, number = current
        return Response(
            {"next_question": _question_payload(next_qa, number), "is_complete": False},
            status=status.HTTP_200_OK,
        )


def _open_session_qa(session_id, question_id):
    return get_object_or_404(
        InterviewQA.objects.select_related("session"),
        id=question_id,
        session_id=session_id,
    )


class InterviewEventView(APIView):
    """Integrity events from the interview room (tab switches, leaving full screen, ...)."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = InterviewEventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        session = get_object_or_404(InterviewSession, id=data["session_id"])
        qa = None
        if data.get("question_id"):
            qa = session.qa_pairs.filter(id=data["question_id"]).first()
        InterviewEvent.objects.create(
            session=session,
            qa=qa,
            event_type=data["event_type"],
            duration_ms=data.get("duration_ms"),
        )
        return Response(status=status.HTTP_201_CREATED)


class RecordingChunkView(APIView):
    """Append one ordered chunk to a question's audio recording."""

    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser]

    def post(self, request):
        serializer = RecordingChunkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        qa = _open_session_qa(data["session_id"], data["question_id"])
        chunk = data["chunk"].read()

        with transaction.atomic():
            recording = (
                InterviewRecording.objects.select_for_update()
                .filter(id=data["recording_id"])
                .first()
            )
            if recording is None:
                if data["seq"] != 0:
                    return Response(
                        {"detail": "Recording must start at chunk 0."},
                        status=status.HTTP_409_CONFLICT,
                    )
                ext = RECORDING_EXTENSIONS[data["mime_type"]]
                recording = InterviewRecording(
                    id=data["recording_id"],
                    session=qa.session,
                    qa=qa,
                    content_type=data["mime_type"],
                )
                recording.file.save(f"{recording.id}.{ext}", ContentFile(chunk), save=False)
            else:
                if recording.qa_id != qa.id:
                    return Response(
                        {"detail": "Recording belongs to another question."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if data["seq"] < recording.next_seq:
                    # Retried upload of a chunk we already have.
                    return Response({"next_seq": recording.next_seq}, status=status.HTTP_200_OK)
                if data["seq"] > recording.next_seq:
                    return Response(
                        {"detail": "Out-of-order chunk.", "next_seq": recording.next_seq},
                        status=status.HTTP_409_CONFLICT,
                    )
                if recording.size_bytes + len(chunk) > MAX_RECORDING_BYTES:
                    return Response(
                        {"detail": "Recording is too long."},
                        status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    )
                with recording.file.open("ab") as f:
                    f.write(chunk)

            recording.next_seq = data["seq"] + 1
            recording.size_bytes += len(chunk)
            recording.save()

        return Response({"next_seq": recording.next_seq}, status=status.HTTP_200_OK)

