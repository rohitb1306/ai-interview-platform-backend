from django.urls import path

from .views import (
    InterviewEventView,
    RecordingChunkView,
    StartInterviewView,
    SubmitAnswerView,
    ValidateTokenView,
)

urlpatterns = [
    path("validate", ValidateTokenView.as_view(), name="interview-validate"),
    path("start", StartInterviewView.as_view(), name="interview-start"),
    path("submit-answer", SubmitAnswerView.as_view(), name="interview-submit-answer"),
    path("event", InterviewEventView.as_view(), name="interview-event"),
    path("recording-chunk", RecordingChunkView.as_view(), name="interview-recording-chunk"),
]
