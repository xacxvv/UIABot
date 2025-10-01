"""OpenAI client wrapper for generating troubleshooting guidance."""

from __future__ import annotations

from typing import Iterable

from openai import OpenAI


class AIAssistant:
    """Thin wrapper around the OpenAI Responses API."""

    def __init__(self, api_key: str, model: str = "gpt-5-nano") -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

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

        response = self._client.responses.create(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": "You are a helpful Mongolian IT support assistant.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        text = response.output_text
        if text is not None:
            return text.strip()

        # Fallback for safety: join string segments if output_text is missing.
        segments: Iterable[str] = (
            part.text
            for item in response.output if hasattr(item, "content")
            for part in getattr(item, "content", [])
            if getattr(part, "type", None) == "output_text" and hasattr(part, "text")
        )
        fallback = "".join(segments).strip()
        if fallback:
            return fallback

        raise RuntimeError("No text returned from OpenAI response")

