"""OpenAI client wrapper for generating troubleshooting guidance."""

from __future__ import annotations

from openai import OpenAI


class AIAssistant:
    """Thin wrapper around the OpenAI chat completions API."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
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

