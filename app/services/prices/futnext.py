"""FUTNext's PC card-price feed; no EA account or Companion session needed."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ...models.schemas import PriceQuote
from ...models.tables import CatalogCard
from .base import PriceUnavailable

PRICE_URL = "https://enhancer-api.futnext.com/players/prices"


class FutnextProvider:
    name = "futnext"
    platform = "pc"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=8.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, card: CatalogCard) -> PriceQuote:
        params = {"ids": str(card.ea_id), "platform": "pc"}
        try:
            response = await self._client.get(PRICE_URL, params=params)
            response.raise_for_status()
            records = response.json()
        except httpx.HTTPStatusError as exc:
            raise PriceUnavailable(self.name, f"FUTNext HTTP {exc.response.status_code} dondurdu.") from exc
        except (httpx.RequestError, ValueError) as exc:
            raise PriceUnavailable(self.name, f"FUTNext yaniti alinamadi: {type(exc).__name__}") from exc

        if not isinstance(records, list):
            raise PriceUnavailable(self.name, "FUTNext beklenmeyen bir yanit dondurdu.")

        record = next(
            (item for item in records if isinstance(item, dict) and item.get("definitionId") == card.ea_id),
            None,
        )
        prices = record.get("prices") if record else None
        price = prices[0] if isinstance(prices, list) and prices else None
        if not isinstance(price, int) or isinstance(price, bool) or price <= 0:
            raise PriceUnavailable(self.name, "FUTNext bu kart icin PC fiyati yayinlamiyor.")

        now = datetime.now(timezone.utc)
        note = "FUTNext PC piyasasi"
        updated_at = record.get("updatedAt")
        if isinstance(updated_at, (int, float)) and not isinstance(updated_at, bool):
            age_minutes = max(0, int((now.timestamp() - updated_at / 1000) // 60))
            note += f"; kaynak {age_minutes} dk once guncellendi"

        return PriceQuote(
            ea_id=card.ea_id,
            price=price,
            platform="pc",
            source=self.name,
            fetched_at=now,
            note=note,
            source_url=str(response.url),
        )
