"""The scan pipeline: screenshot -> card -> price.

Order of operations, and why:
  1. content hash   -- skip a file we have already processed
  2. remembered fix -- a card the user corrected before never asks again
  3. vision         -- name, rating, position, artwork
  4. catalog        -- which player, then which of that player's cards
  5. price          -- only once exactly one card is identified

Ambiguity is never resolved by guessing. When two cards agree on name, rating
and position (Zidane's base icon vs its holographic twin), both are shown and
the user picks; that choice is remembered against the image's perceptual hash.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .catalog.futgg import CatalogError, FutGGCatalog, SitemapEntry
from .repository import Repository
from ..core.events import EventBus
from .matching.matcher import filter_cards, match_player, rank_by_style
from .matching.normalize import fold, slug_to_name
from ..models.schemas import CardReading, ScanResult, ScanSource
from ..models.tables import CatalogCard
from .prices.chain import PriceService
from .recognize.imaging import content_hash, perceptual_hash
from .recognize.base import CardReader, VisionError

logger = logging.getLogger(__name__)


class ScanService:
    def __init__(
        self,
        repo: Repository,
        bus: EventBus,
        reader: CardReader | None,
        prices: PriceService,
        ea_tax_rate: float = 0.05,
    ) -> None:
        self._repo = repo
        self._bus = bus
        self._reader = reader
        self._prices = prices
        self._tax = ea_tax_rate
        self._catalog_lock = asyncio.Lock()
        self.catalog_status = "bos"

    # ---------------------------------------------------------------- catalog
    async def sync_catalog(self, force: bool = False) -> dict:
        """Pull FUT.GG's sitemap into the local index.

        This is the only bulk fetch in the app, and it reads the file FUT.GG
        publishes for crawlers -- not a scrape of every card page. Card details
        are fetched lazily, one player at a time, as cards are actually scanned.
        """
        async with self._catalog_lock:
            if not force and self._repo.player_count() > 0:
                self.catalog_status = "hazir"
                return {
                    "synced": False,
                    "players": self._repo.player_count(),
                    "cards": self._repo.card_count(),
                }

            self.catalog_status = "indiriliyor"
            self._bus.publish("catalog", {"status": self.catalog_status})
            try:
                async with FutGGCatalog() as catalog:
                    entries = await catalog.sitemap_entries()
            except CatalogError as exc:
                self.catalog_status = f"hata: {exc}"
                self._bus.publish("catalog", {"status": self.catalog_status})
                raise

            self._store_entries(entries)
            self.catalog_status = "hazir"
            result = {
                "synced": True,
                "players": self._repo.player_count(),
                "cards": self._repo.card_count(),
            }
            self._bus.publish("catalog", {"status": self.catalog_status, **result})
            logger.info(
                "katalog hazir: %d oyuncu, %d kart", result["players"], result["cards"]
            )
            return result

    def _store_entries(self, entries: list[SitemapEntry]) -> None:
        players: dict[int, tuple[int, str, str]] = {}
        cards: list[tuple[int, int, str, str, str]] = []
        for entry in entries:
            players[entry.base_player_ea_id] = (
                entry.base_player_ea_id, entry.full_slug, slug_to_name(entry.slug)
            )
            cards.append(
                (
                    entry.ea_id, entry.base_player_ea_id, entry.name,
                    entry.full_slug, entry.url,
                )
            )
        self._repo.upsert_players(players.values())
        self._repo.upsert_card_stubs(cards)

    async def ensure_player_cards(self, base_player_ea_id: int) -> list[CatalogCard]:
        """Fill in ratings/positions/artwork for one player, fetching lazily."""
        cards = self._repo.cards_for_player(base_player_ea_id)
        missing = self._repo.cards_missing_details([c.ea_id for c in cards])
        if not missing:
            return cards

        async with FutGGCatalog() as catalog:
            # One page usually describes several of the player's versions.
            first = next(c for c in cards if c.ea_id in missing)
            page = await catalog.card_page(first.url, first.ea_id)
            self._repo.upsert_card(page.primary)
            for sibling in page.siblings:
                if sibling.ea_id and sibling.rating:
                    self._repo.upsert_card(sibling)

            still_missing = self._repo.cards_missing_details([c.ea_id for c in cards])
            for ea_id in still_missing:
                card = self._repo.card(ea_id)
                if card is None:
                    continue
                try:
                    detail = await catalog.card_page(card.url, ea_id)
                except CatalogError as exc:
                    logger.warning("kart %s detayi alinamadi: %s", ea_id, exc)
                    continue
                self._repo.upsert_card(detail.primary)
                await asyncio.sleep(0.3)

        return self._repo.cards_for_player(base_player_ea_id)

    async def add_card_by_ea_id(self, ea_id: int, url: str | None = None) -> CatalogCard:
        """Fetch one specific card and put it in the catalog."""
        known = self._repo.card(ea_id)
        target = url or (known.url if known else None)
        if target is None:
            raise CatalogError(
                f"{ea_id} katalogda yok ve adresi bilinmiyor. Once katalogu guncelle."
            )
        async with FutGGCatalog() as catalog:
            page = await catalog.card_page(target, ea_id)
        self._repo.upsert_card(page.primary)
        for sibling in page.siblings:
            if sibling.ea_id and sibling.rating:
                self._repo.upsert_card(sibling)
        self._repo.upsert_players(
            [(page.primary.base_player_ea_id, page.primary.slug, fold(page.primary.name))]
        )
        return page.primary

    # ------------------------------------------------------------------ scan
    async def process_file(
        self, path: Path, source: ScanSource = "folder"
    ) -> ScanResult | None:
        """Run one screenshot end to end. None means it was a duplicate."""
        digest = content_hash(path)
        if self._repo.scan_exists(digest):
            logger.info("%s zaten islenmis, atlaniyor", path.name)
            return None

        phash = perceptual_hash(path)
        result = ScanResult(
            scan_id=0,
            image_hash=digest,
            image_path=str(path),
            status="error",
            created_at=datetime.now(timezone.utc),
            source=source,
        )
        result.scan_id = self._repo.insert_scan(digest, str(path), "pending", source)

        try:
            await self._run_pipeline(result, path, phash)
        except VisionError as exc:
            result.status = "error"
            result.message = str(exc)
            logger.error("%s okunamadi: %s", path.name, exc)
        except CatalogError as exc:
            result.status = "error"
            result.message = f"Katalog hatasi: {exc}"
            logger.error("%s katalog hatasi: %s", path.name, exc)
        except Exception as exc:  # noqa: BLE001 - one bad file must not kill the watcher
            result.status = "error"
            result.message = f"Beklenmeyen hata: {type(exc).__name__}: {exc}"
            logger.exception("%s islenirken beklenmeyen hata", path.name)

        self._persist(result, phash)
        return result

    async def _run_pipeline(self, result: ScanResult, path: Path, phash: str) -> None:
        remembered = self._repo.correction_for(phash)
        if remembered is not None:
            card = self._repo.card(remembered)
            if card is not None:
                logger.info("%s daha once duzeltilmisti -> %s", path.name, card.ea_id)
                result.card = card
                result.status = "matched"
                result.message = "Daha once duzelttigin kart hatirlandi."
                await self._attach_price(result, card)
                return

        if self._reader is None:
            raise VisionError(
                "Gorsel okuma kapali -- baslangic hatasina bak (.env icindeki "
                "VISION_BACKEND / anahtar / Ollama modeli)."
            )

        reading = await self._reader.read(path)
        result.reading = reading

        if not reading.is_card:
            result.status = "not_a_card"
            result.message = "Kart bulunamadi, atlandi."
            logger.info("%s kart degil, sessizce atlandi", path.name)
            return

        candidates = await self._find_candidates(reading)
        if not candidates:
            result.status = "no_match"
            result.message = (
                f"'{reading.name}' {reading.rating or '?'} "
                f"{reading.position or '?'} icin kart bulunamadi."
            )
            return

        if len(candidates) == 1:
            card = candidates[0]
            result.card = card
            result.status = "matched"
            await self._attach_price(result, card)
            return

        result.candidates = rank_by_style(candidates, reading)
        result.status = "ambiguous"
        result.message = (
            f"{len(candidates)} farkli kart ayni isim/rating/pozisyona sahip. Sen sec."
        )

    async def _find_candidates(self, reading: CardReading) -> list[CatalogCard]:
        if not reading.name:
            return []
        index = self._repo.player_index()
        if not index:
            logger.warning("katalog bos; once senkronize et")
            return []

        hits = match_player(reading.name, index)
        if not hits:
            return []

        pool: list[CatalogCard] = []
        for hit in hits[:2]:  # the top two players, to tolerate a near-miss name
            cards = await self.ensure_player_cards(hit.base_player_ea_id)
            pool.extend(c for c in cards if c.rating is not None)

        return filter_cards(pool, reading)

    async def _attach_price(self, result: ScanResult, card: CatalogCard) -> None:
        quote, failures = await self._prices.get(card)
        result.quote = quote
        result.failures = failures
        if quote is None and not result.message:
            result.message = "Kart tanindi ama fiyat alinamadi."

    # ---------------------------------------------------------------- search
    async def search(self, query: str, limit: int = 12) -> list[dict]:
        """Name search for the in-app picker, filling in details on demand."""
        if not query.strip():
            return []
        hits = match_player(query, self._repo.player_index(), limit=4)
        out: list[dict] = []
        for hit in hits:
            try:
                cards = await self.ensure_player_cards(hit.base_player_ea_id)
            except CatalogError as exc:
                logger.warning("%s kartlari alinamadi: %s", hit.name, exc)
                cards = self._repo.cards_for_player(hit.base_player_ea_id)
            for card in sorted(cards, key=lambda c: -(c.rating or 0)):
                out.append(_card_payload(card))
                if len(out) >= limit:
                    return out
        return out

    # ------------------------------------------------------------- correction
    async def apply_correction(self, scan_id: int, ea_id: int) -> ScanResult:
        """Pin a scan to a specific card and remember it for next time."""
        row = self._repo.get_scan(scan_id)
        if row is None:
            raise ValueError(f"Tarama bulunamadi: {scan_id}")

        card = self._repo.card(ea_id)
        if card is None or card.rating is None:
            card = await self.add_card_by_ea_id(ea_id)

        path = Path(row.image_path)
        phash = perceptual_hash(path) if path.exists() else row.image_hash
        self._repo.remember_correction(phash, ea_id)

        result = ScanResult(
            scan_id=scan_id,
            image_hash=row.image_hash,
            image_path=row.image_path,
            status="matched",
            created_at=datetime.now(timezone.utc),
            card=card,
            message="Secimin kaydedildi, bu gorsel bir daha sorulmayacak.",
        )
        await self._attach_price(result, card)
        self._persist(result, phash)
        return result

    async def refresh_price(self, scan_id: int) -> ScanResult:
        row = self._repo.get_scan(scan_id)
        if row is None:
            raise ValueError(f"Tarama bulunamadi: {scan_id}")
        ea_id = ((row.payload or {}).get("card") or {}).get("ea_id")
        if not ea_id:
            raise ValueError("Bu taramaya bagli bir kart yok.")

        card = self._repo.card(int(ea_id))
        if card is None:
            raise ValueError(f"Kart katalogda yok: {ea_id}")

        quote, failures = await self._prices.get(card, force_refresh=True)
        result = ScanResult(
            scan_id=scan_id,
            image_hash=row.image_hash,
            image_path=row.image_path,
            status="matched",
            created_at=datetime.now(timezone.utc),
            card=card,
            quote=quote,
            failures=failures,
            message=None if quote else "Fiyat yenilenemedi.",
        )
        self._persist(result, None)
        return result

    # ----------------------------------------------------------------- output
    def _persist(self, result: ScanResult, phash: str | None) -> None:
        payload = self.to_payload(result)
        if phash:
            payload["perceptual_hash"] = phash
        self._repo.update_scan(result.scan_id, result.status, payload)
        self._bus.publish("scan", payload)

    def to_payload(self, result: ScanResult) -> dict:
        quote = result.quote
        price = quote.price if quote else None
        payload = {
            "scan_id": result.scan_id,
            "image_hash": result.image_hash,
            "image_path": result.image_path,
            "image_name": Path(result.image_path).name,
            "status": result.status,
            "source": result.source,
            "created_at": result.created_at.isoformat(),
            "message": result.message,
            "reading": asdict(result.reading) if result.reading else None,
            "card": _card_payload(result.card) if result.card else None,
            "candidates": [_card_payload(c) for c in result.candidates],
            "failures": [asdict(f) for f in result.failures],
            "price": None,
        }
        if quote is not None:
            payload["price"] = {
                "value": price,
                "platform": quote.platform,
                "source": quote.source,
                "source_url": quote.source_url,
                "note": quote.note,
                "is_extinct": quote.is_extinct,
                "fetched_at": quote.fetched_at.isoformat(),
                "age_seconds": round(quote.age_seconds),
                "after_tax": int(round(price * (1 - self._tax))) if price else None,
                "tax_rate": self._tax,
            }
        return payload


def _card_payload(card: CatalogCard) -> dict:
    return {
        "ea_id": card.ea_id,
        "base_player_ea_id": card.base_player_ea_id,
        "name": card.name,
        "rating": card.rating,
        "position": card.position,
        "alt_positions": card.alt_positions,
        "version": card.display_version,
        "rarity_name": card.rarity_name,
        "image_url": card.image_url,
        "url": card.url,
    }
