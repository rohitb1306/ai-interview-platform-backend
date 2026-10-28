from django.urls import path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ApplicationAdminViewSet,
    JobAdminViewSet,
    MeView,
    SessionReportView,
    StaffLoginView,
    StatsView,
)

router = SimpleRouter()
router.register("jobs", JobAdminViewSet, basename="admin-job")
router.register("applications", ApplicationAdminViewSet, basename="admin-application")

urlpatterns = [
    path("auth/login", StaffLoginView.as_view(), name="admin-login"),
    path("auth/refresh", TokenRefreshView.as_view(), name="admin-token-refresh"),
    path("auth/me", MeView.as_view(), name="admin-me"),
    path("stats", StatsView.as_view(), name="admin-stats"),
    path("sessions/<uuid:pk>/", SessionReportView.as_view(), name="admin-session-report"),
] + router.urls
