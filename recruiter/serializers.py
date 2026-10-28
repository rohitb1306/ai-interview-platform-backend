from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from applications.models import Application
from interviews.models import (
    InterviewEvent,
    InterviewEventType,
    InterviewRecording,
    InterviewSession,
)
from interviews.serializers import InterviewQASerializer
from jobs.models import JobPosition


class StaffTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT login that only admits staff users."""

    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.is_staff:
            raise AuthenticationFailed("This account does not have recruiter access.")
        data["user"] = StaffUserSerializer(self.user).data
        return data


class StaffUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()


class JobAdminSerializer(serializers.ModelSerializer):
    application_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = JobPosition
        fields = [
            "id",
            "title",
            "department",
            "raw_jd_text",
            "required_skills",
            "created_at",
            "application_count",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_required_skills(self, value):
        if not isinstance(value, list) or not all(isinstance(s, str) for s in value):
            raise serializers.ValidationError("Must be a list of skill names.")
        return [s.strip() for s in value if s.strip()]


class ApplicationListSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source="candidate.full_name")
    candidate_email = serializers.EmailField(source="candidate.email")
    job_id = serializers.UUIDField(source="job_position.id")
    job_title = serializers.CharField(source="job_position.title")
    match_score = serializers.FloatField(allow_null=True)
    interview_score = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            "id",
            "candidate_name",
            "candidate_email",
            "job_id",
            "job_title",
            "status",
            "match_score",
            "interview_score",
            "created_at",
        ]

    def get_interview_score(self, application):
        # Sessions are prefetched newest-first by the view.
        for session in application.sessions.all():
            if session.overall_score is not None:
                return float(session.overall_score)
        return None


def _absolute_url(serializer, file_field):
    if not file_field:
        return None
    request = serializer.context.get("request")
    return request.build_absolute_uri(file_field.url) if request else file_field.url


class SessionAdminSerializer(serializers.ModelSerializer):
    """Per-session summary shown on the candidate page."""

    overall_score = serializers.FloatField(allow_null=True)
    answered_count = serializers.SerializerMethodField()
    focus_lost_count = serializers.SerializerMethodField()
    fullscreen_exit_count = serializers.SerializerMethodField()
    face_flag_count = serializers.SerializerMethodField()

    class Meta:
        model = InterviewSession
        fields = [
            "id",
            "started_at",
            "completed_at",
            "overall_score",
            "answered_count",
            "focus_lost_count",
            "fullscreen_exit_count",
            "face_flag_count",
        ]

    def get_answered_count(self, session):
        return sum(1 for qa in session.qa_pairs.all() if qa.candidate_answer_text is not None)

    def _count_events(self, session, event_type):
        return sum(1 for e in session.events.all() if e.event_type == event_type)

    def get_focus_lost_count(self, session):
        return self._count_events(session, InterviewEventType.FOCUS_LOST)

    def get_fullscreen_exit_count(self, session):
        return self._count_events(session, InterviewEventType.FULLSCREEN_EXIT)

    def get_face_flag_count(self, session):
        return self._count_events(session, InterviewEventType.NO_FACE) + self._count_events(
            session, InterviewEventType.MULTIPLE_FACES
        )


class RecordingSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = InterviewRecording
        fields = ["id", "url", "content_type", "size_bytes", "created_at", "updated_at"]

    def get_url(self, recording):
        return _absolute_url(self, recording.file)


class QAReportSerializer(InterviewQASerializer):
    evaluation_score = serializers.FloatField(allow_null=True)
    recordings = RecordingSerializer(many=True)

    class Meta(InterviewQASerializer.Meta):
        fields = InterviewQASerializer.Meta.fields + ["recordings"]


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewEvent
        fields = ["id", "event_type", "qa_id", "duration_ms", "created_at"]


class SessionReportSerializer(serializers.ModelSerializer):
    """Full interview report for recruiters: scores, answers, audio and integrity log."""

    overall_score = serializers.FloatField(allow_null=True)
    application_id = serializers.UUIDField(source="application.id")
    candidate_name = serializers.CharField(source="application.candidate.full_name")
    candidate_email = serializers.EmailField(source="application.candidate.email")
    job_title = serializers.CharField(source="application.job_position.title")
    match_score = serializers.FloatField(source="application.match_score", allow_null=True)
    gap_analysis = serializers.JSONField(source="application.gap_analysis", allow_null=True)
    qa_pairs = QAReportSerializer(many=True)
    events = EventSerializer(many=True)

    class Meta:
        model = InterviewSession
        fields = [
            "id",
            "application_id",
            "candidate_name",
            "candidate_email",
            "job_title",
            "match_score",
            "gap_analysis",
            "started_at",
            "completed_at",
            "overall_score",
            "final_feedback",
            "qa_pairs",
            "events",
        ]


class ApplicationDetailSerializer(ApplicationListSerializer):
    resume_url = serializers.SerializerMethodField()
    sessions = SessionAdminSerializer(many=True)
    active_invite_expires_at = serializers.SerializerMethodField()

    class Meta(ApplicationListSerializer.Meta):
        fields = ApplicationListSerializer.Meta.fields + [
            "gap_analysis",
            "extracted_text",
            "resume_url",
            "sessions",
            "active_invite_expires_at",
        ]

    def get_resume_url(self, application):
        return _absolute_url(self, application.resume_file)

    def get_active_invite_expires_at(self, application):
        token = (
            application.tokens.filter(is_used=False, expires_at__gt=timezone.now())
            .order_by("-expires_at")
            .first()
        )
        return token.expires_at if token else None
