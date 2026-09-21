from django.urls import path

from .views import ApplyView

urlpatterns = [
    path("apply", ApplyView.as_view(), name="apply"),
]
