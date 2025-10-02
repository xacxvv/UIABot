"""OpenAI client wrapper for generating troubleshooting guidance."""

from __future__ import annotations

import logging

from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)


logger = logging.getLogger(__name__)


class AIAssistant:
    """Thin wrapper around the OpenAI Responses API."""

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

        try:
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
            # SDK >= 1.0 exposes ``output_text``; older deployments store the
            # message inside ``choices``.
            content = getattr(response, "output_text", None)
            if content:
                return content.strip()
            return response.choices[0].message.content.strip()
        except AuthenticationError:
            logger.exception("OpenAI auth error")
            return "⚠️ OpenAI API түлхүүр буруу эсвэл идэвхгүй байна. Тохиргоог шалгана уу."
        except RateLimitError:
            logger.exception("OpenAI rate limit")
            return "⚠️ OpenAI талд түр дараалал дүүрсэн байна. Дараа дахин оролдоно уу."
        except (BadRequestError, APIStatusError, APIConnectionError) as exc:
            logger.exception("OpenAI call failed: %s", exc)
            return "⚠️ AI зөвлөгөө авахад алдаа гарлаа. Сүлжээ/загварын тохиргоог шалгана уу."
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception("Unexpected OpenAI error: %s", exc)
            return "⚠️ Тодорхойгүй алдаа. Логийг шалгана уу."

