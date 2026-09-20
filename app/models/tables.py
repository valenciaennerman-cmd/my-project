"""SQLModel tables.

`ea_id` is the primary key for a card everywhere in this app: it is the only
value that is unique per card *version*. Name, rating, position and even
rarity name are shared between variants -- both 94-rated Zidanes are
`rarityName="Base Icon"`, `rarityEaId=12`, CAM. See research/FINDINGS.md.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, Index
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CatalogPlayer(SQLModel, table=True):
    """One real player; may own many cards."""

    __tablename__ = "catalog_player"

    base_player_ea_id: int = Field(primary_key=True)
    slug: str
    name_folded: str = Field(index=True)


class CatalogCard(SQLModel, table=True):
    """One specific card version."""

    __tablename__ = "catalog_card"

    ea_id: int = Field(primary_key=True)
    base_player_ea_id: int = Field(index=True, foreign_key="catalog_player.base_player_ea_id")
    name: str
    slug: str
    url: str

    rating: int | None = Field(default=None, index=True)
    position: str | None = Field(default=None, index=True)
    alt_positions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    rarity_name: str | None = None
    # The only field that spells out "Holographic", i.e. the one that tells
    # otherwise-identical cards apart.
    version_label: str | None = None
    image_url: str | None = None
    details_fetched: bool = Field(default=False)

    @property
    def display_version(self) -> str:
        return self.version_label or self.rarity_name or "?"


class FutwizMap(SQLModel, table=True):
    """eaId -> FUTWIZ's own card id, resolved once and reused forever."""

    __tablename__ = "futwiz_map"

    ea_id: int = Field(primary_key=True)
    futwiz_id: int
    slug: str
    mapped_at: datetime = Field(default_factory=utcnow)


class Scan(SQLModel, table=True):
    """One processed screenshot."""

    __tablename__ = "scan"
    __table_args__ = (Index("idx_scan_created", "created_at"),)

    id: int | None = Field(default=None, primary_key=True)
    # SHA-256 of the file bytes: the de-duplication key.
    image_hash: str = Field(unique=True, index=True)
    image_path: str
    source: str = Field(default="folder")
    status: str
    created_at: datetime = Field(default_factory=utcnow)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Correction(SQLModel, table=True):
    """A card the user picked by hand, keyed on the image's perceptual hash so
    a second screenshot of the same card recalls the choice."""

    __tablename__ = "correction"

    image_hash: str = Field(primary_key=True)
    ea_id: int
    created_at: datetime = Field(default_factory=utcnow)


class PriceCache(SQLModel, table=True):
    """Last known price per card per platform."""

    __tablename__ = "price_cache"

    ea_id: int = Field(primary_key=True)
    platform: str = Field(primary_key=True)
    source: str
    price: int | None = None
    is_extinct: bool = False
    note: str | None = None
    source_url: str | None = None
    fetched_at: datetime = Field(default_factory=utcnow)


class Meta(SQLModel, table=True):
    """Small key/value store for app state."""

    __tablename__ = "meta"

    key: str = Field(primary_key=True)
    value: str
