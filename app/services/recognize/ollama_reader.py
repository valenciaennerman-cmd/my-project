"""Card reading through a local Ollama model.

Free and offline, but the model must actually accept images. Ollama reports
this: `/api/show` lists `vision` in `capabilities`, and a model without it
answers an image request with HTTP 400. That check runs once at startup so the
failure is a clear message instead of a 400 on the first screenshot.

Measured on this machine (2026-09-20):
    qwen3:30b-a3b   completion, tools, thinking            -> no vision, 400
    qwen3.5:4b      (no capabilities reported)             -> no vision, 400
    qwen3.5:0.8b    completion, vision, tools, thinking    -> works
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

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

# Ollama's structured output takes a plain JSON Schema. Descriptions are kept:
# small models lean on them heavily.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": dict(SCHEMA_PROPERTIES),
    "required": SCHEMA_REQUIRED,
}


class OllamaCardReader:
    """Reads one screenshot into a CardReading using a local Ollama model."""

    name = "ollama"

    def __init__(
        self,
        host: str,
        model: str,
        think: bool = False,
        timeout: float = 180.0,
        num_predict: int = 700,
    ) -> None:
        self._host = host.rstrip("/")
        self.model = model
        self._think = think
        self._num_predict = num_predict
        self._client = httpx.AsyncClient(timeout=timeout)
        self._checked = False

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- startup check -----------------------------------------------------
    async def verify(self) -> None:
        """Fail loudly at startup if the model cannot see images."""
        try:
            response = await self._client.post(
                f"{self._host}/api/show", json={"model": self.model}, timeout=30.0
            )
        except httpx.HTTPError as exc:
            raise VisionError(
                f"Ollama'ya baglanilamadi ({self._host}). Calisiyor mu? ({exc})"
            ) from exc

        if response.status_code == 404:
            raise VisionError(
                f"Ollama'da '{self.model}' yok. 'ollama pull {self.model}' calistir."
            )
        if response.status_code != 200:
            raise VisionError(
                f"Ollama /api/show HTTP {response.status_code} dondu ({self.model})."
            )

        capabilities = response.json().get("capabilities") or []
        if "vision" not in capabilities:
            raise VisionError(
                f"'{self.model}' goruntu okuyamiyor (yetenekleri: "
                f"{', '.join(capabilities) or 'bildirilmedi'}). Kart okumak icin "
                f"'vision' yetenegi olan bir model gerekiyor; "
                f"'ollama show {self.model}' ile dogrulayabilirsin."
            )
        self._checked = True
        logger.info(
            "ollama hazir: %s (yetenekler: %s)", self.model, ", ".join(capabilities)
        )

    # -- reading -----------------------------------------------------------
    async def read(self, path: Path) -> CardReading:
        if not self._checked:
            await self.verify()

        image = prepare_for_vision(path)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_PROMPT,
                    "images": [image.base64_data],
                },
            ],
            "stream": False,
            "think": self._think,
            "format": RESPONSE_SCHEMA,
            "options": {"temperature": 0, "num_predict": self._num_predict},
        }

        try:
            response = await self._client.post(f"{self._host}/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise VisionError(
                f"Ollama zaman asimina ugradi ({self.model}). Daha kucuk bir model "
                f"dene ya da OLLAMA_TIMEOUT degerini artir."
            ) from exc
        except httpx.HTTPError as exc:
            raise VisionError(f"Ollama'ya baglanilamadi: {exc}") from exc

        if response.status_code == 400:
            raise VisionError(
                f"Ollama '{self.model}' icin goruntuyu reddetti (HTTP 400). "
                f"Bu model goruntu okuyamiyor."
            )
        if response.status_code != 200:
            raise VisionError(f"Ollama HTTP {response.status_code}: {response.text[:160]}")

        body = response.json()
        content = (body.get("message") or {}).get("content", "")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise VisionError(
                f"Ollama gecerli JSON dondurmedi: {content[:120]!r}"
            ) from exc
        if not isinstance(data, dict):
            raise VisionError(f"Ollama beklenmeyen bir yanit dondurdu: {type(data).__name__}")

        logger.info(
            "ollama %s -> %s (%s ms)",
            path.name, data.get("name"),
            round((body.get("total_duration") or 0) / 1e6),
        )
        return to_reading(data)
