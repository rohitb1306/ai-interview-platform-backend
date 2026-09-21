from django.urls import path

from .views import InterviewReportView, StartInterviewView, SubmitAnswerView, ValidateTokenView

urlpatterns = [
    path("validate", ValidateTokenView.as_view(), name="interview-validate"),
    path("start", StartInterviewView.as_view(), name="interview-start"),
    path("submit-answer", SubmitAnswerView.as_view(), name="interview-submit-answer"),
    path("report/<uuid:session_id>", InterviewReportView.as_view(), name="interview-report"),
]
