"""Cache + fallback chain in front of the price providers.

Behaviour the app depends on:
  * a fresh cached quote short-circuits the whole chain;
  * providers are tried in configured order and the first success wins;
  * every failure is collected and handed back, so the UI can say *why* there
    is no price instead of showing a blank;
  * a stale cached quote is better than nothing -- if every provider fails we
    return the stale entry, flagged with its real age.
"""
from __future__ import annotations

import logging

from ..repository import Repository
from ...models.schemas import PriceFailure, PriceQuote
from ...models.tables import CatalogCard
from .base import PriceProvider, PriceUnavailable

logger = logging.getLogger(__name__)


class PriceService:
    def __init__(
        self, providers: list[PriceProvider], repo: Repository, cache_ttl: int = 420
    ) -> None:
        self._providers = providers
        self._repo = repo
        self._ttl = cache_ttl

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self._providers]

    async def aclose(self) -> None:
        for provider in self._providers:
            await provider.aclose()

    def _cached(self, ea_id: int, platform: str) -> PriceQuote | None:
        row = self._repo.cached_price(ea_id, platform)
        if row is None:
            return None
        return PriceQuote(
            ea_id=ea_id,
            price=row.price,
            platform=platform,  # type: ignore[arg-type]
            source=row.source,
            fetched_at=row.fetched_at,
            is_extinct=row.is_extinct,
            note=row.note,
            source_url=row.source_url,
        )

    def cached_fresh(self, ea_id: int) -> PriceQuote | None:
        """The freshest non-expired quote for this card, if any."""
        for provider in self._providers:
            quote = self._cached(ea_id, provider.platform)
            if quote is not None and quote.age_seconds < self._ttl:
                return quote
        return None

    async def get(
        self, card: CatalogCard, force_refresh: bool = False
    ) -> tuple[PriceQuote | None, list[PriceFailure]]:
        failures: list[PriceFailure] = []

        if not force_refresh:
            fresh = self.cached_fresh(card.ea_id)
            if fresh is not None:
                logger.debug(
                    "cache hit eaId=%s (%.0f sn)", card.ea_id, fresh.age_seconds
                )
                return fresh, failures

        for provider in self._providers:
            try:
                quote = await provider.fetch(card)
            except PriceUnavailable as exc:
                logger.info("%s basarisiz: %s", provider.name, exc.reason)
                failures.append(PriceFailure(source=provider.name, reason=exc.reason))
                continue
            except Exception as exc:  # noqa: BLE001 - never let one source kill the scan
                logger.exception("%s beklenmeyen hata", provider.name)
                failures.append(
                    PriceFailure(
                        source=provider.name,
                        reason=f"Beklenmeyen hata: {type(exc).__name__}: {exc}",
                    )
                )
                continue

            self._repo.store_price(
                ea_id=card.ea_id, platform=quote.platform, source=quote.source,
                price=quote.price, is_extinct=quote.is_extinct, note=quote.note,
                source_url=quote.source_url, fetched_at=quote.fetched_at,
            )
            # Cached reads deliberately do not land here: a point means the
            # price was actually observed at that moment.
            if quote.price is not None:
                self._repo.record_price_point(
                    ea_id=card.ea_id, platform=quote.platform, price=quote.price,
                    source=quote.source, recorded_at=quote.fetched_at,
                )
            return quote, failures

        # Everything failed -- a stale number with an honest age beats nothing.
        for provider in self._providers:
            stale = self._cached(card.ea_id, provider.platform)
            if stale is not None:
                logger.info(
                    "tum kaynaklar basarisiz; %.0f sn eski cache kullaniliyor",
                    stale.age_seconds,
                )
                return stale, failures

        return None, failures
