"""Where card readers are wired up.

To add a backend: write a module implementing `CardReader`, then add one line to
`BUILDERS` and set `VISION_BACKEND` in `.env`.
"""
from __future__ import annotations

import logging
from typing import Callable

from ...core.config import Settings
from .anthropic_reader import AnthropicCardReader
from .base import CardReader, VisionError
from .ollama_reader import OllamaCardReader

logger = logging.getLogger(__name__)

BUILDERS: dict[str, Callable[[Settings], CardReader]] = {
    "anthropic": lambda s: AnthropicCardReader(s.anthropic_api_key, s.vision_model),
    "ollama": lambda s: OllamaCardReader(
        host=s.ollama_host,
        model=s.ollama_model,
        think=s.ollama_think,
        timeout=s.ollama_timeout,
    ),
}


def build_reader(settings: Settings) -> CardReader:
    """Construct the configured reader, or raise VisionError with guidance."""
    backend = settings.vision_backend.strip().lower()
    builder = BUILDERS.get(backend)
    if builder is None:
        raise VisionError(
            f"Bilinmeyen VISION_BACKEND: {backend!r}. "
            f"Tanimli olanlar: {', '.join(sorted(BUILDERS))}."
        )
    reader = builder(settings)
    logger.info("kart okuyucu: %s (%s)", reader.name, reader.model)
    return reader
