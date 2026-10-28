import tempfile
import uuid
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from applications.models import Application, ApplicationStatus
from applications.tasks import issue_interview_token
from candidates.models import Candidate
from jobs.models import JobPosition

from .models import InterviewEvent, InterviewQA, InterviewRecording
from .serializers import TOTAL_QUESTIONS

API = "/api/v1/interview"


class FakeLLM:
    def __init__(self):
        self.questions_generated = 0
        self.evaluations = 0
        self.fail_next = False

    def _maybe_fail(self):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("LLM down")

    def generate_question(self, job, application, previous_qa, question_number):
        self._maybe_fail()
        self.questions_generated += 1
        return {"text": f"Question {question_number}?", "question_type": "TECHNICAL"}

    def evaluate_answer(self, question_text, answer_text):
        self._maybe_fail()
        self.evaluations += 1
        return {"score": 80, "feedback": "Good."}

    def generate_final_feedback(self, qa_pairs):
        self._maybe_fail()
        return "Solid candidate."


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ResumableInterviewTests(APITestCase):
    def setUp(self):
        job = JobPosition.objects.create(title="Backend Engineer", raw_jd_text="Python")
        candidate = Candidate.objects.create(full_name="Ada", email="ada@example.com")
        self.application = Application.objects.create(
            candidate=candidate,
            job_position=job,
            resume_file=SimpleUploadedFile("cv.pdf", b"%PDF"),
            status=ApplicationStatus.SHORTLISTED,
        )
        self.token = issue_interview_token(self.application)
        self.llm = FakeLLM()
        patcher = mock.patch("interviews.views.get_llm", return_value=self.llm)
        patcher.start()
        self.addCleanup(patcher.stop)

    def start(self):
        return self.client.post(f"{API}/start", {"token": self.token}, format="json")

    def answer(self, session_id, question_id):
        return self.client.post(
            f"{API}/submit-answer",
            {"session_id": session_id, "question_id": question_id, "answer_text": "An answer here."},
            format="json",
        )

    def test_reopening_link_resumes_same_question(self):
        first = self.start().data
        again = self.start().data
        self.assertEqual(first["session_id"], again["session_id"])
        self.assertEqual(first["question"]["id"], again["question"]["id"])
        self.assertEqual(self.llm.questions_generated, 1)

    def test_resume_after_answering_continues_from_next_question(self):
        first = self.start().data
        q2 = self.answer(first["session_id"], first["question"]["id"]).data["next_question"]
        self.assertEqual(q2["number"], 2)

        validate = self.client.get(f"{API}/validate", {"token": self.token}).data
        self.assertTrue(validate["in_progress"])
        self.assertEqual(validate["answered_count"], 1)

        resumed = self.start().data
        self.assertEqual(resumed["question"]["id"], q2["id"])
        self.assertEqual(resumed["question"]["number"], 2)

    def test_ai_failure_on_start_keeps_link_usable(self):
        self.llm.fail_next = True
        self.assertEqual(self.start().status_code, 503)
        res = self.start()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["question"]["number"], 1)

    def test_ai_failure_after_answer_saved_does_not_regrade_on_retry(self):
        first = self.start().data
        session_id, qid = first["session_id"], first["question"]["id"]
        # Grading succeeds, then generating the next question fails.
        with mock.patch.object(self.llm, "generate_question", side_effect=RuntimeError):
            self.assertEqual(self.answer(session_id, qid).status_code, 503)
        self.assertTrue(InterviewQA.objects.get(id=qid).candidate_answer_text)

        res = self.answer(session_id, qid)
        self.assertEqual(res.data["next_question"]["number"], 2)
        self.assertEqual(self.llm.evaluations, 1)

    def test_completion_invalidates_link(self):
        data = self.start().data
        session_id, question = data["session_id"], data["question"]
        for _ in range(TOTAL_QUESTIONS):
            res = self.answer(session_id, question["id"]).data
            question = res["next_question"]
        self.assertTrue(res["is_complete"])

        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.COMPLETED)
        self.assertEqual(self.start().status_code, 400)

    def test_report_is_not_public(self):
        session_id = self.start().data["session_id"]
        self.assertEqual(self.client.get(f"{API}/report/{session_id}").status_code, 404)

    def test_event_logging(self):
        data = self.start().data
        res = self.client.post(
            f"{API}/event",
            {
                "session_id": data["session_id"],
                "question_id": data["question"]["id"],
                "event_type": "FOCUS_RETURNED",
                "duration_ms": 4200,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        event = InterviewEvent.objects.get()
        self.assertEqual(event.duration_ms, 4200)
        self.assertEqual(str(event.qa_id), str(data["question"]["id"]))

    def upload_chunk(self, data, recording_id, seq, payload):
        return self.client.post(
            f"{API}/recording-chunk",
            {
                "session_id": data["session_id"],
                "question_id": data["question"]["id"],
                "recording_id": recording_id,
                "seq": seq,
                "mime_type": "video/webm;codecs=vp8,opus",
                "chunk": SimpleUploadedFile("c.webm", payload, content_type="audio/webm"),
            },
            format="multipart",
        )

    def test_recording_chunks_append_in_order(self):
        data = self.start().data
        rid = str(uuid.uuid4())
        self.assertEqual(self.upload_chunk(data, rid, 1, b"x").status_code, 409)
        self.assertEqual(self.upload_chunk(data, rid, 0, b"aaa").status_code, 200)
        self.assertEqual(self.upload_chunk(data, rid, 1, b"bbb").status_code, 200)
        # A retried chunk is acknowledged without being appended twice.
        self.assertEqual(self.upload_chunk(data, rid, 1, b"bbb").status_code, 200)
        self.assertEqual(self.upload_chunk(data, rid, 3, b"ddd").status_code, 409)

        recording = InterviewRecording.objects.get(id=rid)
        self.assertTrue(recording.file.name.endswith(".webm"))
        self.assertEqual(recording.content_type, "video/webm")
        with recording.file.open("rb") as f:
            self.assertEqual(f.read(), b"aaabbb")
        self.assertEqual(recording.next_seq, 2)
