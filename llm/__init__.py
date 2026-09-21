from django.conf import settings

_provider_instance = None


def get_llm():
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    provider = settings.LLM_PROVIDER.lower()
    if provider == "openai":
        from .openai_provider import OpenAIProvider

        _provider_instance = OpenAIProvider()
    else:
        from .gemini import GeminiProvider

        _provider_instance = GeminiProvider()
    return _provider_instance
