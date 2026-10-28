from django.db import transaction
from django.db.models import Avg, Count, Prefetch, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from applications.models import Application, ApplicationStatus
from applications.tasks import (
    dispatch_invite_email,
    dispatch_rejection_email,
    interview_url_for,
    issue_interview_token,
    parse_and_screen_resume,
)
from interviews.models import InterviewSession
from jobs.models import JobPosition

from .serializers import (
    ApplicationDetailSerializer,
    ApplicationListSerializer,
    JobAdminSerializer,
    SessionReportSerializer,
    StaffTokenObtainPairSerializer,
    StaffUserSerializer,
)


class StaffLoginView(TokenObtainPairView):
    serializer_class = StaffTokenObtainPairSerializer


class MeView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(StaffUserSerializer(request.user).data)


class StatsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        by_status = dict(
            Application.objects.values_list("status").annotate(n=Count("id")).order_by()
        )
        completed_sessions = InterviewSession.objects.filter(completed_at__isnull=False)
        avg_match = Application.objects.aggregate(v=Avg("match_score"))["v"]
        avg_interview = completed_sessions.aggregate(v=Avg("overall_score"))["v"]

        recent = (
            Application.objects.select_related("candidate", "job_position")
            .prefetch_related(_sessions_newest_first())
            .order_by("-created_at")[:5]
        )

        return Response(
            {
                "total_jobs": JobPosition.objects.count(),
                "total_applications": sum(by_status.values()),
                "by_status": {s: by_status.get(s, 0) for s in ApplicationStatus.values},
                "completed_interviews": completed_sessions.count(),
                "avg_match_score": round(float(avg_match), 2) if avg_match is not None else None,
                "avg_interview_score": (
                    round(float(avg_interview), 2) if avg_interview is not None else None
                ),
                "recent_applications": ApplicationListSerializer(recent, many=True).data,
            }
        )


class JobAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = JobAdminSerializer

    def get_queryset(self):
        return JobPosition.objects.annotate(application_count=Count("applications")).order_by(
            "-created_at"
        )

    def destroy(self, request, *args, **kwargs):
        job = self.get_object()
        if job.applications.exists():
            return Response(
                {"detail": "This role has applications and can't be deleted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


def _sessions_newest_first():
    return Prefetch(
        "sessions",
        queryset=InterviewSession.objects.order_by("-started_at").prefetch_related(
            "qa_pairs", "events"
        ),
    )


class ApplicationAdminViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        return ApplicationDetailSerializer if self.action == "retrieve" else ApplicationListSerializer

    def get_queryset(self):
        qs = (
            Application.objects.select_related("candidate", "job_position")
            .prefetch_related(_sessions_newest_first())
            .order_by("-created_at")
        )
        params = self.request.query_params
        if job_id := params.get("job"):
            qs = qs.filter(job_position_id=job_id)
        if status_filter := params.get("status"):
            qs = qs.filter(status=status_filter)
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(candidate__full_name__icontains=q) | Q(candidate__email__icontains=q)
            )
        return qs

    def _detail_response(self, application, **extra):
        application = self.get_queryset().get(pk=application.pk)
        data = ApplicationDetailSerializer(application, context={"request": self.request}).data
        return Response({**data, **extra})

    @action(detail=True, methods=["post"])
    def shortlist(self, request, pk=None):
        """Manually shortlist and (re)send an interview link, bypassing AI screening.

        Mid-interview, the new link resumes the same session where the candidate left off.
        """
        application = self.get_object()
        if application.status == ApplicationStatus.COMPLETED:
            return Response(
                {"detail": "Candidate has already finished the interview."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            application.tokens.filter(is_used=False).update(is_used=True)
            raw_token = issue_interview_token(application)
            if application.status != ApplicationStatus.INTERVIEW_IN_PROGRESS:
                application.status = ApplicationStatus.SHORTLISTED
                application.save(update_fields=["status"])

        # Run inline so it works without a Celery worker; console backend prints to runserver.
        dispatch_invite_email(str(application.id), raw_token)
        return self._detail_response(application, interview_url=interview_url_for(raw_token))

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        application = self.get_object()
        if application.status == ApplicationStatus.INTERVIEW_IN_PROGRESS:
            return Response(
                {"detail": "Candidate is in the middle of an interview."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            application.tokens.filter(is_used=False).update(is_used=True)
            application.status = ApplicationStatus.REJECTED
            application.save(update_fields=["status"])

        dispatch_rejection_email(str(application.id))
        return self._detail_response(application)

    @action(detail=True, methods=["post"])
    def rescreen(self, request, pk=None):
        """Re-run AI resume screening (e.g. after adding an LLM API key)."""
        application = self.get_object()
        if application.status in (
            ApplicationStatus.INTERVIEW_IN_PROGRESS,
            ApplicationStatus.COMPLETED,
        ):
            return Response(
                {"detail": "Can't re-screen after the interview has started."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        application.status = ApplicationStatus.PENDING
        application.save(update_fields=["status"])
        parse_and_screen_resume.delay(str(application.id))
        return self._detail_response(application)


class SessionReportView(RetrieveAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = SessionReportSerializer
    queryset = InterviewSession.objects.select_related(
        "application__candidate", "application__job_position"
    ).prefetch_related("qa_pairs__recordings", "events")
