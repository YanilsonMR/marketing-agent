"""
LLM Service — OpenRouter integration via OpenAI SDK.
"""

from openai import OpenAI

from config.settings import Settings


class LLMService:
    """Handles LLM calls via OpenRouter."""

    def __init__(self, settings: Settings) -> None:
        self._client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
        self._model = settings.openrouter_model

    def chat(self, system: str, user: str, max_tokens: int = 1024) -> str:
        """Send a system+user message pair and return the text response."""
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content
