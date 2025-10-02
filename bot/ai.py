"""OpenAI client wrapper for generating troubleshooting guidance."""

from __future__ import annotations

import logging

from openai import OpenAI


logger = logging.getLogger(__name__)


class AIAssistant:
    """Thin wrapper around the OpenAI chat completions API."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def verify_model(self) -> bool:
        """Best-effort check that the configured model is accessible."""

        try:
            self._client.models.retrieve(self._model)
        except Exception as exc:  # pragma: no cover - depends on external API
            logger.warning(
                "OpenAI rejected model '%s'. The bot may fail to respond until the "
                "configuration is updated. Details: %s",
                self._model,
                exc,
            )
            return False

        return True

    def generate_guidance(self, issue_type: str, description: str) -> str:
        """Generate a step-by-step troubleshooting guide."""

        prompt = (
            "Та боловсролын байгууллагын мэдээллийн технологийн дэмжлэгийн инженер. "
            "Доорх мэдээллийг ашиглаад хэрэглэгчийн асуудлыг шийдвэрлэхэд зориулсан "
            "5-8 алхам бүхий дэлгэрэнгүй зааварчилгаа боловсруулна уу. Алхам бүрийг "
            "1., 2. гэж дугаарласан жагсаалтаар харуулж, энгийн монгол хэлээр тайлбарлаарай.\n\n"
            f"Асуудлын төрөл: {issue_type}\n"
            f"Хэрэглэгчийн тайлбар: {description}\n"
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful Mongolian IT support assistant.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        return response.choices[0].message.content.strip()

