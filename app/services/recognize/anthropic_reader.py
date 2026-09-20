"""Card reading through the Anthropic API.

Pinned to a strict tool schema so the result is always the same shape; free-form
JSON parsing is never used.
"""
from __future__ import annotations

import logging
from pathlib import Path

import anthropic

from ...models.schemas import CardReading
from .base import (
    SCHEMA_PROPERTIES,
    SCHEMA_REQUIRED,
    SYSTEM_PROMPT,
    USER_PROMPT,
    VisionError,
    to_reading,
)
from .imaging import prepare_for_vision

logger = logging.getLogger(__name__)

TOOL_NAME = "report_card"


def _nullable(schema: dict) -> dict:
    """Anthropic tool schemas express 'may be absent' as a nullable type."""
    out = dict(schema)
    kind = out.get("type")
    if kind in ("string", "integer"):
        out["type"] = [kind, "null"]
    return out


CARD_TOOL: dict = {
    "name": TOOL_NAME,
    "description": (
        "Report what the screenshot shows. Call this exactly once, for the "
        "single most prominent player card."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            key: _nullable(value) if key != "is_card" and key != "confidence" else value
            for key, value in SCHEMA_PROPERTIES.items()
        },
        "required": SCHEMA_REQUIRED,
    },
}


class AnthropicCardReader:
    """Reads one screenshot into a CardReading using Claude."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str, max_retries: int = 2) -> None:
        if not api_key:
            raise VisionError(
                "ANTHROPIC_API_KEY tanimli degil. .env dosyasina ekle "
                "(ornek icin .env.example), ya da VISION_BACKEND=ollama yap."
            )
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=max_retries)
        self.model = model

    async def aclose(self) -> None:
        await self._client.close()

    async def read(self, path: Path) -> CardReading:
        image = prepare_for_vision(path)
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=[CARD_TOOL],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": image.media_type,
                                    "data": image.base64_data,
                                },
                            },
                            {"type": "text", "text": USER_PROMPT},
                        ],
                    }
                ],
            )
        except anthropic.AuthenticationError as exc:
            raise VisionError("Anthropic API anahtari gecersiz.") from exc
        except anthropic.RateLimitError as exc:
            raise VisionError("Anthropic API kota siniri asildi, biraz sonra dene.") from exc
        except anthropic.APIStatusError as exc:
            raise VisionError(f"Anthropic API hatasi ({exc.status_code}).") from exc
        except anthropic.APIConnectionError as exc:
            raise VisionError("Anthropic API'ye baglanilamadi (ag hatasi).") from exc

        if response.stop_reason == "refusal":
            raise VisionError("Model bu goruntuyu okumayi reddetti.")

        payload = next(
            (b.input for b in response.content if b.type == "tool_use" and b.name == TOOL_NAME),
            None,
        )
        if not isinstance(payload, dict):
            raise VisionError("Model beklenen arac cagrisini dondurmedi.")

        logger.info(
            "anthropic %s -> %s (giris %s / cikis %s token)",
            path.name, payload.get("name"),
            response.usage.input_tokens, response.usage.output_tokens,
        )
        return to_reading(payload)
