from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from .models import JobPosition
from .serializers import JobPositionSerializer


class JobListView(ListAPIView):
    queryset = JobPosition.objects.order_by("title")
    serializer_class = JobPositionSerializer
    permission_classes = [AllowAny]
