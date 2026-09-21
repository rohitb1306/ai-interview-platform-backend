import json
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...

    @abstractmethod
    def _complete_json(self, prompt: str) -> dict:
        """Send `prompt`, return the parsed JSON object from the model's reply."""
        ...

    def analyze_resume(self, resume_text: str, job) -> dict:
        prompt = f"""You are screening a resume against a job description.

Job title: {job.title}
Required skills: {json.dumps(job.required_skills)}
Job description:
{job.raw_jd_text}

Resume text:
{resume_text[:8000]}

Return ONLY a JSON object with this exact shape:
{{
  "matched_skills": [list of required skills the resume demonstrates],
  "missing_skills": [list of required skills the resume does not demonstrate],
  "missing_context": "one or two sentence summary of gaps",
  "skill_coverage_ratio": number between 0 and 1 (matched_skills / total required_skills)
}}"""
        return self._complete_json(prompt)

    def generate_question(self, job, application, previous_qa: list, question_number: int) -> dict:
        history = "\n".join(
            f"Q{i + 1} ({qa.question_type}): {qa.question_text}\nA: {qa.candidate_answer_text}"
            for i, qa in enumerate(previous_qa)
        ) or "(no questions asked yet)"
        gap_analysis = json.dumps(application.gap_analysis or {})
        prompt = f"""You are conducting a live AI interview for the role "{job.title}".

Candidate resume gap analysis: {gap_analysis}
Interview so far:
{history}

Generate question number {question_number} of 5. Vary question types across the interview
(TECHNICAL, BEHAVIORAL, SYSTEM_DESIGN) and probe the missing/weak areas from the gap analysis
where relevant. Do not repeat a previous question.

Return ONLY a JSON object with this exact shape:
{{
  "text": "the interview question",
  "question_type": "TECHNICAL" | "BEHAVIORAL" | "SYSTEM_DESIGN"
}}"""
        return self._complete_json(prompt)

    def evaluate_answer(self, question_text: str, answer_text: str) -> dict:
        prompt = f"""Evaluate this interview answer.

Question: {question_text}
Candidate's answer: {answer_text}

Score the answer from 0 to 100 on correctness, clarity, and depth. Give brief actionable feedback.

Return ONLY a JSON object with this exact shape:
{{
  "score": number between 0 and 100,
  "feedback": "one or two sentences of feedback"
}}"""
        return self._complete_json(prompt)

    def generate_final_feedback(self, qa_pairs: list) -> str:
        history = "\n".join(
            f"Q{i + 1} ({qa.question_type}): {qa.question_text}\n"
            f"A: {qa.candidate_answer_text}\n"
            f"Score: {qa.evaluation_score}, Feedback: {qa.ai_feedback}"
            for i, qa in enumerate(qa_pairs)
        )
        prompt = f"""Here is a completed AI interview transcript with per-question scores:

{history}

Write a concise (3-5 sentence) overall summary of the candidate's performance: key strengths,
key weaknesses, and a hiring recommendation.

Return ONLY a JSON object with this exact shape:
{{
  "summary": "the overall feedback text"
}}"""
        result = self._complete_json(prompt)
        return result.get("summary", "")
