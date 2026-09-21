from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from candidates.models import Candidate
from jobs.models import JobPosition

from .models import Application
from .serializers import ApplicationResponseSerializer, ApplySerializer
from .tasks import parse_and_screen_resume


class ApplyView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        candidate, _ = Candidate.objects.get_or_create(
            email=data["email"], defaults={"full_name": data["full_name"]}
        )
        job_position = JobPosition.objects.get(id=data["job_id"])

        application = Application.objects.create(
            candidate=candidate,
            job_position=job_position,
            resume_file=data["resume_file"],
        )

        parse_and_screen_resume.delay(str(application.id))

        response = ApplicationResponseSerializer(
            {
                "message": "Application received. Verification in progress.",
                "application_id": application.id,
            }
        )
        return Response(response.data, status=status.HTTP_202_ACCEPTED)
