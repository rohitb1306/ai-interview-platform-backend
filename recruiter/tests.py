import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from applications.models import Application, ApplicationStatus
from candidates.models import Candidate
from interviews.models import InterviewToken
from jobs.models import JobPosition

API = "/api/v1/admin"


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class RecruiterApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user("recruiter", "r@example.com", "pw12345!", is_staff=True)
        self.regular = User.objects.create_user("someone", "s@example.com", "pw12345!")
        self.job = JobPosition.objects.create(
            title="Backend Engineer", raw_jd_text="Python, Django", required_skills=["Python"]
        )
        candidate = Candidate.objects.create(full_name="Ada Lovelace", email="ada@example.com")
        self.application = Application.objects.create(
            candidate=candidate,
            job_position=self.job,
            resume_file=SimpleUploadedFile("cv.pdf", b"%PDF-1.4"),
        )

    def login(self, username="recruiter"):
        res = self.client.post(f"{API}/auth/login", {"username": username, "password": "pw12345!"})
        if res.status_code == 200:
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        return res

    def test_login_rejects_non_staff(self):
        self.assertEqual(self.login("someone").status_code, 401)

    def test_endpoints_require_staff(self):
        self.assertEqual(self.client.get(f"{API}/stats").status_code, 401)
        self.assertEqual(self.client.get(f"{API}/applications/").status_code, 401)

    def test_stats(self):
        self.login()
        res = self.client.get(f"{API}/stats")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["total_jobs"], JobPosition.objects.count())
        self.assertEqual(res.data["by_status"]["PENDING"], 1)
        self.assertEqual(len(res.data["recent_applications"]), 1)

    def test_job_crud_and_protected_delete(self):
        self.login()
        res = self.client.post(
            f"{API}/jobs/",
            {"title": "Data Scientist", "raw_jd_text": "ML", "required_skills": [" SQL ", ""]},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["required_skills"], ["SQL"])

        res = self.client.patch(f"{API}/jobs/{res.data['id']}/", {"department": "AI"}, format="json")
        self.assertEqual(res.data["department"], "AI")
        self.assertEqual(self.client.delete(f"{API}/jobs/{res.data['id']}/").status_code, 204)

        self.assertEqual(self.client.delete(f"{API}/jobs/{self.job.id}/").status_code, 400)

    def test_application_filters_and_detail(self):
        self.login()
        res = self.client.get(f"{API}/applications/", {"q": "ada", "status": "PENDING"})
        self.assertEqual(len(res.data), 1)
        res = self.client.get(f"{API}/applications/", {"status": "REJECTED"})
        self.assertEqual(len(res.data), 0)

        res = self.client.get(f"{API}/applications/{self.application.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["candidate_name"], "Ada Lovelace")
        self.assertTrue(res.data["resume_url"].startswith("http://testserver/media/"))

    def test_shortlist_issues_single_valid_link_and_emails(self):
        self.login()
        first = self.client.post(f"{API}/applications/{self.application.id}/shortlist/")
        second = self.client.post(f"{API}/applications/{self.application.id}/shortlist/")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["status"], ApplicationStatus.SHORTLISTED)
        self.assertNotEqual(first.data["interview_url"], second.data["interview_url"])
        self.assertIsNotNone(second.data["active_invite_expires_at"])
        self.assertEqual(InterviewToken.objects.filter(is_used=False).count(), 1)
        self.assertEqual(len(mail.outbox), 2)

        token = second.data["interview_url"].split("token=")[1]
        res = self.client.get("/api/v1/interview/validate", {"token": token})
        self.assertEqual(res.status_code, 200)

    def test_reject_revokes_link(self):
        self.login()
        self.client.post(f"{API}/applications/{self.application.id}/shortlist/")
        res = self.client.post(f"{API}/applications/{self.application.id}/reject/")
        self.assertEqual(res.data["status"], ApplicationStatus.REJECTED)
        self.assertIsNone(res.data["active_invite_expires_at"])
        self.assertFalse(InterviewToken.objects.filter(is_used=False).exists())

    def test_resend_mid_interview_keeps_status(self):
        self.login()
        self.application.status = ApplicationStatus.INTERVIEW_IN_PROGRESS
        self.application.save()
        res = self.client.post(f"{API}/applications/{self.application.id}/shortlist/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], ApplicationStatus.INTERVIEW_IN_PROGRESS)

    def test_cannot_shortlist_after_completion(self):
        self.login()
        self.application.status = ApplicationStatus.COMPLETED
        self.application.save()
        res = self.client.post(f"{API}/applications/{self.application.id}/shortlist/")
        self.assertEqual(res.status_code, 400)

    @mock.patch("recruiter.views.parse_and_screen_resume.delay")
    def test_rescreen_queues_task(self, delay):
        self.login()
        res = self.client.post(f"{API}/applications/{self.application.id}/rescreen/")
        self.assertEqual(res.status_code, 200)
        delay.assert_called_once_with(str(self.application.id))

    def test_session_report_is_staff_only_and_complete(self):
        session = self.application.sessions.create()
        qa = session.qa_pairs.create(question_text="Q?", question_type="TECHNICAL")
        session.events.create(qa=qa, event_type="FOCUS_LOST")
        url = f"{API}/sessions/{session.id}/"
        self.assertEqual(self.client.get(url).status_code, 401)

        self.login()
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["candidate_name"], "Ada Lovelace")
        self.assertEqual(len(res.data["qa_pairs"]), 1)
        self.assertEqual(res.data["qa_pairs"][0]["recordings"], [])
        self.assertEqual(res.data["events"][0]["event_type"], "FOCUS_LOST")

        detail = self.client.get(f"{API}/applications/{self.application.id}/").data
        self.assertEqual(detail["sessions"][0]["focus_lost_count"], 1)
