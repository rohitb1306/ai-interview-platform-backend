import json

from django.conf import settings
from google import genai
from google.genai import types

from .base import LLMProvider

GENERATION_MODEL = "gemini-2.0-flash"
EMBEDDING_MODEL = "text-embedding-004"


class GeminiProvider(LLMProvider):
    def __init__(self):
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def embed(self, text: str) -> list[float]:
        result = self._client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
        )
        return list(result.embeddings[0].values)

    def _complete_json(self, prompt: str) -> dict:
        response = self._client.models.generate_content(
            model=GENERATION_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return json.loads(response.text)
