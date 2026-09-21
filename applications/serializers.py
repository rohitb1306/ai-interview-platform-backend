from rest_framework import serializers

from jobs.models import JobPosition

ALLOWED_RESUME_EXTENSIONS = (".pdf", ".docx")
MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024


class ApplySerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=100)
    email = serializers.EmailField(max_length=150)
    job_id = serializers.UUIDField()
    resume_file = serializers.FileField()

    def validate_job_id(self, value):
        if not JobPosition.objects.filter(id=value).exists():
            raise serializers.ValidationError("Job position not found.")
        return value

    def validate_resume_file(self, value):
        name = value.name.lower()
        if not name.endswith(ALLOWED_RESUME_EXTENSIONS):
            raise serializers.ValidationError("Resume must be a .pdf or .docx file.")
        if value.size > MAX_RESUME_SIZE_BYTES:
            raise serializers.ValidationError("Resume must be 5MB or smaller.")
        return value


class ApplicationResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    application_id = serializers.UUIDField()
