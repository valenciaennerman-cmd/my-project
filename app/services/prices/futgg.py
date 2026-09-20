"""FUT.GG price provider -- CONSOLE (PS/Xbox) market only.

Kept as a clearly-labelled fallback, never as the default for a PC player.
FUT.GG's price payload is tagged `platform: "ps5"` and contains no PC figure at
all (verified against the live payload), so anything this returns must be shown
as a console number in the UI.

The price is not in the server-rendered HTML -- the page fetches it itself from
a signed endpoint. We therefore load the page in a browser and read what it
renders, rather than reproducing the signing flow (which robots.txt disallows
and which is an access control we will not work around).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from playwright.async_api import Page

from ...models.schemas import PriceQuote
from ...models.tables import CatalogCard
from .base import PriceUnavailable
from .browser import BrowserPool, BrowserUnavailable, ChallengeNotCleared

logger = logging.getLogger(__name__)

_LOWEST_BIN_JS = """() => {
  const isPrice = (t) => /^\\d{1,3}([,.]\\d{3})+$/.test(t);
  const leaves = [...document.querySelectorAll('*')].filter(e => !e.children.length);
  const idx = leaves.findIndex(e => /lowest\\s*bin/i.test(e.textContent.trim()));
  const out = { price: null, age: null, extinct: false };
  if (idx >= 0) {
    for (let j = idx + 1; j < Math.min(idx + 10, leaves.length); j++) {
      const t = leaves[j].textContent.trim();
      if (!out.age && /(ago|min|hour|day|sec)/i.test(t)) out.age = t;
      if (/^extinct$/i.test(t)) { out.extinct = true; break; }
      if (isPrice(t)) { out.price = t; break; }
    }
  }
  if (!out.price && !out.extinct) {
    const any = leaves.find(e => isPrice(e.textContent.trim()));
    if (any) out.price = any.textContent.trim();
  }
  return out;
}"""


class FutGGPriceProvider:
    """Reads FUT.GG's console lowest-BIN through a real browser."""

    name = "futgg"
    platform = "console"

    def __init__(self, pool: BrowserPool) -> None:
        self._pool = pool

    async def aclose(self) -> None:
        return None

    async def fetch(self, card: CatalogCard) -> PriceQuote:
        if not card.url:
            raise PriceUnavailable(self.name, "Kartin FUT.GG adresi yok.")

        page = await self._open(card.url)
        try:
            await self._wait_for_price(page)
            data = await page.evaluate(_LOWEST_BIN_JS)
        finally:
            await self._pool.release(page)

        if data.get("extinct"):
            return PriceQuote(
                ea_id=card.ea_id, price=None, platform="console", source=self.name,
                fetched_at=datetime.now(timezone.utc), is_extinct=True,
                note="FUT.GG: extinct (KONSOL piyasasi)", source_url=card.url,
            )

        raw = data.get("price")
        price = int(re.sub(r"[^0-9]", "", raw)) if raw else None
        if price is None:
            raise PriceUnavailable(self.name, "Sayfada fiyat bulunamadi.")

        age = data.get("age")
        return PriceQuote(
            ea_id=card.ea_id, price=price, platform="console", source=self.name,
            fetched_at=datetime.now(timezone.utc),
            note=f"KONSOL fiyati (PC degil), sitede {age}" if age else "KONSOL fiyati (PC degil)",
            source_url=card.url,
        )

    async def _open(self, url: str) -> Page:
        try:
            return await self._pool.open(url)
        except ChallengeNotCleared as exc:
            raise PriceUnavailable(self.name, f"Bot dogrulamasi gecilemedi: {exc}") from exc
        except BrowserUnavailable as exc:
            raise PriceUnavailable(self.name, str(exc)) from exc

    async def _wait_for_price(self, page: Page) -> None:
        try:
            await page.wait_for_function(
                "() => [...document.querySelectorAll('*')].some(e => !e.children.length && "
                "(/^\\d{1,3}([,.]\\d{3})+$/.test(e.textContent.trim()) || "
                "/^extinct$/i.test(e.textContent.trim())))",
                timeout=12_000,
            )
        except Exception:  # noqa: BLE001 - absence handled by the caller
            logger.info("fut.gg: fiyat dugumu 12 sn icinde gorunmedi")
