from rest_framework import serializers

from .models import InterviewQA

TOTAL_QUESTIONS = 5


class TokenValidateResponseSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    candidate_name = serializers.CharField(required=False)
    job_title = serializers.CharField(required=False)


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


class InterviewReportSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    overall_score = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    final_feedback = serializers.CharField(allow_null=True, allow_blank=True)
    gap_analysis = serializers.JSONField(allow_null=True)
    qa_pairs = InterviewQASerializer(many=True)
