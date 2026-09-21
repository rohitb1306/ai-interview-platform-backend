import json

from django.conf import settings
from openai import OpenAI

from .base import LLMProvider

GENERATION_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"


class OpenAIProvider(LLMProvider):
    def __init__(self):
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        return list(response.data[0].embedding)

    def _complete_json(self, prompt: str) -> dict:
        response = self._client.chat.completions.create(
            model=GENERATION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
