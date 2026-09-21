import hashlib

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from applications.models import ApplicationStatus
from llm import get_llm

from .models import InterviewQA, InterviewSession, InterviewToken
from .serializers import (
    TOTAL_QUESTIONS,
    InterviewReportSerializer,
    InterviewStartSerializer,
    SubmitAnswerSerializer,
    TokenValidateResponseSerializer,
)


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

        data = TokenValidateResponseSerializer(
            {
                "valid": True,
                "candidate_name": token.application.candidate.full_name,
                "job_title": token.application.job_position.title,
            }
        ).data
        return Response(data, status=status.HTTP_200_OK)


class StartInterviewView(APIView):
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

            token.is_used = True
            token.save(update_fields=["is_used"])

            application = token.application
            session = InterviewSession.objects.create(
                application=application, started_at=timezone.now()
            )
            application.status = ApplicationStatus.INTERVIEW_IN_PROGRESS
            application.save(update_fields=["status"])

        question_data = get_llm().generate_question(
            job=application.job_position,
            application=application,
            previous_qa=[],
            question_number=1,
        )
        first_question = InterviewQA.objects.create(
            session=session,
            question_text=question_data["text"],
            question_type=question_data["question_type"],
        )

        return Response(
            {
                "session_id": session.id,
                "question": {
                    "id": first_question.id,
                    "text": first_question.question_text,
                    "number": 1,
                    "total": TOTAL_QUESTIONS,
                },
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
            InterviewQA, id=data["question_id"], session_id=data["session_id"]
        )
        session = qa.session
        application = session.application
        llm = get_llm()

        evaluation = llm.evaluate_answer(qa.question_text, data["answer_text"])
        qa.candidate_answer_text = data["answer_text"]
        qa.evaluation_score = evaluation.get("score")
        qa.ai_feedback = evaluation.get("feedback", "")
        qa.save(update_fields=["candidate_answer_text", "evaluation_score", "ai_feedback"])

        answered_qa = list(session.qa_pairs.all())
        answered_count = len(answered_qa)

        if answered_count < TOTAL_QUESTIONS:
            next_question_data = llm.generate_question(
                job=application.job_position,
                application=application,
                previous_qa=answered_qa,
                question_number=answered_count + 1,
            )
            next_qa = InterviewQA.objects.create(
                session=session,
                question_text=next_question_data["text"],
                question_type=next_question_data["question_type"],
            )
            return Response(
                {
                    "next_question": {
                        "id": next_qa.id,
                        "text": next_qa.question_text,
                        "number": answered_count + 1,
                        "total": TOTAL_QUESTIONS,
                    },
                    "is_complete": False,
                },
                status=status.HTTP_200_OK,
            )

        scores = [qa.evaluation_score for qa in answered_qa if qa.evaluation_score is not None]
        session.overall_score = round(sum(scores) / len(scores), 2) if scores else None
        session.final_feedback = llm.generate_final_feedback(answered_qa)
        session.completed_at = timezone.now()
        session.save(update_fields=["overall_score", "final_feedback", "completed_at"])

        application.status = ApplicationStatus.COMPLETED
        application.save(update_fields=["status"])

        return Response({"next_question": None, "is_complete": True}, status=status.HTTP_200_OK)


class InterviewReportView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, session_id):
        session = get_object_or_404(
            InterviewSession.objects.select_related("application").prefetch_related("qa_pairs"),
            id=session_id,
        )
        data = InterviewReportSerializer(
            {
                "session_id": session.id,
                "overall_score": session.overall_score,
                "final_feedback": session.final_feedback,
                "gap_analysis": session.application.gap_analysis,
                "qa_pairs": session.qa_pairs.all(),
            }
        ).data
        return Response(data, status=status.HTTP_200_OK)
