"""The CardReader interface, plus the prompt and schema every backend shares.

Adding a reader means one new module implementing `CardReader` and one line in
`registry.py` -- the same shape as the price providers.

The prompt and schema live here so a cloud model and a local model are asked
exactly the same question; otherwise their benchmark numbers would not be
comparable.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ...models.schemas import CardReading
from ..matching.normalize import normalize_position, normalize_rating

CARD_TYPES = (
    "bronze", "silver", "gold", "gold_rare", "totw", "icon",
    "hero", "hall_of_fut", "special", "unknown",
)

SYSTEM_PROMPT = """You read EA Sports FC 27 Ultimate Team player cards from screenshots.

Card layout: the large number in the top-left is the overall rating, the short
code directly beneath it is the primary position, and the player's name runs
across the card near the bottom above the six stat abbreviations (PAC/SHO/PAS/
DRI/DEF/PHY, or DIV/HAN/KIC/REF/SPD/POS for goalkeepers).

Rules:
- Read the rating from the top-left corner only. Never report a stat value.
- Copy the name exactly as printed, keeping accents and non-English letters.
- '++' or '+' markers next to the position are chemistry indicators, not the position.
- Card artwork matters: note whether the card looks holographic, meaning an
  iridescent pink/purple shimmer over the base design.
- If the image is a full screen with several cards, describe the single largest
  or most central card.
- If no player card is visible (a menu, a pitch view, a desktop screenshot),
  set is_card to false and leave the other fields empty.
- Never guess a name you cannot actually read. Lower the confidence instead."""

USER_PROMPT = "Read this card."

# One schema, expressed two ways: Anthropic tool-use wants nullable fields,
# Ollama's structured output is happier with plain types and an "unknown".
SCHEMA_PROPERTIES: dict[str, Any] = {
    "is_card": {
        "type": "boolean",
        "description": "True only if an EA FC player card is clearly visible.",
    },
    "name": {
        "type": "string",
        "description": "Player name exactly as printed on the card, with accents.",
    },
    "rating": {
        "type": "integer",
        "description": "Overall rating, the large number in the top-left corner (1-99).",
    },
    "position": {
        "type": "string",
        "description": "Primary position under the rating, e.g. ST, CAM, GK, CDM.",
    },
    "card_type": {
        "type": "string",
        "enum": list(CARD_TYPES),
        "description": "Best-guess card family from the artwork.",
    },
    "card_style_description": {
        "type": "string",
        "description": (
            "Short description of the artwork: dominant colours, texture, and "
            "whether it looks holographic (pink/purple iridescent sheen). Say "
            "'holographic' explicitly when it does."
        ),
    },
    "confidence": {
        "type": "number",
        "description": "0.0-1.0 confidence in name, rating and position together.",
    },
}
SCHEMA_REQUIRED = list(SCHEMA_PROPERTIES)


class VisionError(RuntimeError):
    """The card could not be read. Carries a message meant for the user."""


@runtime_checkable
class CardReader(Protocol):
    """One way of turning a screenshot into a CardReading."""

    name: str
    model: str

    async def read(self, path: Path) -> CardReading:
        """Read the card in `path`. Raises VisionError when it cannot."""
        ...

    async def aclose(self) -> None:
        """Release any client resources."""
        ...


def to_reading(payload: dict) -> CardReading:
    """Normalise whatever the model returned into a CardReading."""
    if not payload.get("is_card"):
        return CardReading(
            is_card=False,
            card_style_description=payload.get("card_style_description") or None,
            confidence=_as_float(payload.get("confidence")),
            raw=payload,
        )

    card_type = (payload.get("card_type") or "").strip().lower() or None
    if card_type == "unknown":
        card_type = None

    return CardReading(
        is_card=True,
        name=(payload.get("name") or "").strip() or None,
        rating=normalize_rating(payload.get("rating")),
        position=normalize_position(payload.get("position")),
        card_type=card_type,
        card_style_description=(payload.get("card_style_description") or "").strip() or None,
        confidence=_as_float(payload.get("confidence")),
        raw=payload,
    )


def _as_float(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
