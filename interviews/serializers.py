from rest_framework import serializers

from .models import InterviewEventType, InterviewQA

TOTAL_QUESTIONS = 5


class TokenValidateResponseSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    candidate_name = serializers.CharField(required=False)
    job_title = serializers.CharField(required=False)
    in_progress = serializers.BooleanField(required=False)
    answered_count = serializers.IntegerField(required=False)
    total_questions = serializers.IntegerField(required=False)


class InterviewStartSerializer(serializers.Serializer):
    token = serializers.CharField()


class QuestionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    text = serializers.CharField()
    number = serializers.IntegerField()
    total = serializers.IntegerField(default=TOTAL_QUESTIONS)


class SubmitAnswerSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    question_id = serializers.UUIDField()
    answer_text = serializers.CharField()


class InterviewQASerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewQA
        fields = [
            "id",
            "question_text",
            "question_type",
            "candidate_answer_text",
            "evaluation_score",
            "ai_feedback",
        ]


class InterviewEventCreateSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    question_id = serializers.UUIDField(required=False, allow_null=True)
    event_type = serializers.ChoiceField(choices=InterviewEventType.choices)
    duration_ms = serializers.IntegerField(required=False, allow_null=True, min_value=0)


ALLOWED_RECORDING_TYPES = ("video/webm", "video/mp4", "audio/webm", "audio/ogg", "audio/mp4")
MAX_CHUNK_BYTES = 4 * 1024 * 1024
MAX_RECORDING_BYTES = 200 * 1024 * 1024


class RecordingChunkSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    question_id = serializers.UUIDField()
    recording_id = serializers.UUIDField()
    seq = serializers.IntegerField(min_value=0)
    mime_type = serializers.CharField(max_length=50)
    chunk = serializers.FileField()

    def validate_mime_type(self, value):
        base = value.split(";")[0].strip().lower()
        if base not in ALLOWED_RECORDING_TYPES:
            raise serializers.ValidationError("Unsupported recording format.")
        return base

    def validate_chunk(self, value):
        if value.size > MAX_CHUNK_BYTES:
            raise serializers.ValidationError("Chunk too large.")
        return value
