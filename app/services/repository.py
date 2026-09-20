"""All database access lives here.

Nothing outside this module opens a session, so transactions and the SQLite
connection stay in one place.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Sequence

from sqlalchemy import func
from sqlalchemy.engine import Engine
from sqlmodel import col, select

from ..core.db import session_scope
from ..models.tables import (
    CatalogCard,
    CatalogPlayer,
    Correction,
    FutwizMap,
    Meta,
    PriceCache,
    Scan,
)

logger = logging.getLogger(__name__)


def _aware(value: datetime) -> datetime:
    """SQLite gives naive datetimes back; treat them as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class Repository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ----------------------------------------------------------------- meta
    def get_meta(self, key: str) -> str | None:
        with session_scope(self._engine) as session:
            row = session.get(Meta, key)
            return row.value if row else None

    def set_meta(self, key: str, value: str) -> None:
        with session_scope(self._engine) as session:
            row = session.get(Meta, key)
            if row is None:
                session.add(Meta(key=key, value=value))
            else:
                row.value = value
                session.add(row)

    # -------------------------------------------------------------- catalog
    def upsert_players(self, rows: Iterable[tuple[int, str, str]]) -> None:
        with session_scope(self._engine) as session:
            for base_id, slug, name_folded in rows:
                player = session.get(CatalogPlayer, base_id)
                if player is None:
                    session.add(
                        CatalogPlayer(
                            base_player_ea_id=base_id, slug=slug, name_folded=name_folded
                        )
                    )
                else:
                    player.slug = slug
                    player.name_folded = name_folded
                    session.add(player)

    def upsert_card_stubs(self, rows: Iterable[tuple[int, int, str, str, str]]) -> int:
        """Insert cards known only from the sitemap. Existing rows are left alone."""
        added = 0
        with session_scope(self._engine) as session:
            known = set(session.exec(select(CatalogCard.ea_id)).all())
            for ea_id, base_id, name, slug, url in rows:
                if ea_id in known:
                    continue
                session.add(
                    CatalogCard(
                        ea_id=ea_id, base_player_ea_id=base_id,
                        name=name, slug=slug, url=url,
                    )
                )
                known.add(ea_id)
                added += 1
        return added

    def upsert_card(self, card: CatalogCard, details_fetched: bool = True) -> None:
        """Merge a fully-read card, never downgrading a known field to None."""
        with session_scope(self._engine) as session:
            existing = session.get(CatalogCard, card.ea_id)
            if existing is None:
                card.details_fetched = details_fetched
                session.add(card)
                return
            existing.base_player_ea_id = card.base_player_ea_id or existing.base_player_ea_id
            existing.name = card.name or existing.name
            existing.slug = card.slug or existing.slug
            existing.url = card.url or existing.url
            existing.rating = card.rating if card.rating is not None else existing.rating
            existing.position = card.position or existing.position
            existing.alt_positions = card.alt_positions or existing.alt_positions
            existing.rarity_name = card.rarity_name or existing.rarity_name
            existing.version_label = card.version_label or existing.version_label
            existing.image_url = card.image_url or existing.image_url
            existing.details_fetched = existing.details_fetched or details_fetched
            session.add(existing)

    def player_index(self) -> dict[str, tuple[int, str]]:
        with session_scope(self._engine) as session:
            rows = session.exec(select(CatalogPlayer)).all()
        return {r.name_folded: (r.base_player_ea_id, r.slug) for r in rows}

    def player_count(self) -> int:
        with session_scope(self._engine) as session:
            return int(
                session.exec(select(func.count()).select_from(CatalogPlayer)).one()
            )

    def card_count(self) -> int:
        with session_scope(self._engine) as session:
            return int(
                session.exec(select(func.count()).select_from(CatalogCard)).one()
            )

    def cards_for_player(self, base_player_ea_id: int) -> list[CatalogCard]:
        with session_scope(self._engine) as session:
            return list(
                session.exec(
                    select(CatalogCard)
                    .where(CatalogCard.base_player_ea_id == base_player_ea_id)
                    .order_by(col(CatalogCard.rating).desc())
                ).all()
            )

    def card(self, ea_id: int) -> CatalogCard | None:
        with session_scope(self._engine) as session:
            return session.get(CatalogCard, ea_id)

    def cards_missing_details(self, ea_ids: Sequence[int]) -> list[int]:
        if not ea_ids:
            return []
        with session_scope(self._engine) as session:
            return list(
                session.exec(
                    select(CatalogCard.ea_id).where(
                        col(CatalogCard.ea_id).in_(list(ea_ids)),
                        col(CatalogCard.details_fetched).is_(False),
                    )
                ).all()
            )

    # --------------------------------------------------------- futwiz bridge
    def futwiz_id(self, ea_id: int) -> tuple[int, str] | None:
        with session_scope(self._engine) as session:
            row = session.get(FutwizMap, ea_id)
            return (row.futwiz_id, row.slug) if row else None

    def set_futwiz_id(self, ea_id: int, futwiz_id: int, slug: str) -> None:
        with session_scope(self._engine) as session:
            row = session.get(FutwizMap, ea_id)
            if row is None:
                session.add(FutwizMap(ea_id=ea_id, futwiz_id=futwiz_id, slug=slug))
            else:
                row.futwiz_id = futwiz_id
                row.slug = slug
                row.mapped_at = datetime.now(timezone.utc)
                session.add(row)

    # ----------------------------------------------------------------- scans
    def scan_exists(self, image_hash: str) -> bool:
        with session_scope(self._engine) as session:
            return session.exec(
                select(Scan.id).where(Scan.image_hash == image_hash)
            ).first() is not None

    def insert_scan(
        self, image_hash: str, image_path: str, status: str, source: str = "folder"
    ) -> int:
        with session_scope(self._engine) as session:
            scan = Scan(
                image_hash=image_hash, image_path=image_path,
                status=status, source=source, payload={},
            )
            session.add(scan)
            session.flush()
            return int(scan.id)  # type: ignore[arg-type]

    def update_scan(self, scan_id: int, status: str, payload: dict) -> None:
        with session_scope(self._engine) as session:
            scan = session.get(Scan, scan_id)
            if scan is None:
                logger.warning("guncellenecek tarama yok: %s", scan_id)
                return
            scan.status = status
            scan.payload = payload
            session.add(scan)

    def get_scan(self, scan_id: int) -> Scan | None:
        with session_scope(self._engine) as session:
            return session.get(Scan, scan_id)

    def recent_scans(self, limit: int = 25) -> list[dict]:
        with session_scope(self._engine) as session:
            rows = session.exec(
                select(Scan).order_by(col(Scan.id).desc()).limit(limit)
            ).all()
        out = []
        for row in rows:
            payload = dict(row.payload or {})
            payload.update(
                scan_id=row.id,
                status=row.status,
                created_at=_aware(row.created_at).isoformat(),
                image_hash=row.image_hash,
                image_path=row.image_path,
                source=row.source,
            )
            out.append(payload)
        return out

    # ----------------------------------------------------------- corrections
    def correction_for(self, image_hash: str) -> int | None:
        with session_scope(self._engine) as session:
            row = session.get(Correction, image_hash)
            return row.ea_id if row else None

    def remember_correction(self, image_hash: str, ea_id: int) -> None:
        with session_scope(self._engine) as session:
            row = session.get(Correction, image_hash)
            if row is None:
                session.add(Correction(image_hash=image_hash, ea_id=ea_id))
            else:
                row.ea_id = ea_id
                row.created_at = datetime.now(timezone.utc)
                session.add(row)

    # ---------------------------------------------------------- price cache
    def cached_price(self, ea_id: int, platform: str) -> PriceCache | None:
        with session_scope(self._engine) as session:
            row = session.get(PriceCache, (ea_id, platform))
            if row is not None:
                row.fetched_at = _aware(row.fetched_at)
            return row

    def store_price(
        self, ea_id: int, platform: str, source: str, price: int | None,
        is_extinct: bool, note: str | None, source_url: str | None,
        fetched_at: datetime,
    ) -> None:
        with session_scope(self._engine) as session:
            row = session.get(PriceCache, (ea_id, platform))
            if row is None:
                session.add(
                    PriceCache(
                        ea_id=ea_id, platform=platform, source=source, price=price,
                        is_extinct=is_extinct, note=note, source_url=source_url,
                        fetched_at=fetched_at,
                    )
                )
                return
            row.source = source
            row.price = price
            row.is_extinct = is_extinct
            row.note = note
            row.source_url = source_url
            row.fetched_at = fetched_at
            session.add(row)
