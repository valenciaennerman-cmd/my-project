"""Transfer objects that are not persisted.

Persisted shapes live in `app/models/tables.py`; `CatalogCard` there doubles as
the in-memory card object, so there is exactly one definition of a card.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from .tables import CatalogCard

Platform = Literal["pc", "console"]
ScanStatus = Literal["pending", "not_a_card", "no_match", "ambiguous", "matched", "error"]
ScanSource = Literal["folder", "clipboard"]


@dataclass(slots=True)
class CardReading:
    """What the vision model saw in a screenshot."""

    is_card: bool
    name: str | None = None
    rating: int | None = None
    position: str | None = None
    card_type: str | None = None
    card_style_description: str | None = None
    confidence: float = 0.0
    raw: dict | None = None

    @classmethod
    def not_a_card(cls, reason: str = "") -> CardReading:
        return cls(is_card=False, card_style_description=reason or None)


@dataclass(slots=True)
class PriceQuote:
    """A price from one provider."""

    ea_id: int
    price: int | None
    platform: Platform
    source: str
    fetched_at: datetime
    is_extinct: bool = False
    is_untradeable: bool = False
    note: str | None = None
    source_url: str | None = None

    @property
    def age_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.fetched_at).total_seconds()


@dataclass(slots=True)
class PriceFailure:
    """Why a price could not be fetched -- surfaced, never swallowed."""

    source: str
    reason: str


@dataclass(slots=True)
class ScanResult:
    """Everything the UI needs to render one processed screenshot."""

    scan_id: int
    image_hash: str
    image_path: str
    status: ScanStatus
    created_at: datetime
    source: ScanSource = "folder"
    reading: CardReading | None = None
    card: CatalogCard | None = None
    candidates: list[CatalogCard] = field(default_factory=list)
    quote: PriceQuote | None = None
    failures: list[PriceFailure] = field(default_factory=list)
    message: str | None = None
