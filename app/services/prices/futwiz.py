"""FUTWIZ price provider -- the PC transfer market.

This is the primary source because PC is a separate market from PS/Xbox in
FC 27 and the gap is large (measured: Iniesta 92 Icon, console 1 370 000 vs PC
2 850 000). A console price would be a confidently wrong number, which is worse
than no number.

Only `/en/fc27/player/...` pages are used; FUTWIZ's robots.txt allows those and
disallows the filtered list pages, which we never touch. The site's own search
box is driven rather than any internal endpoint.

Card identity: FUTWIZ numbers cards itself, but every player page prints the EA
"Card ID". That is the same value as FUT.GG's `eaId`, so it is used to confirm a
match, and the resulting eaId -> futwizId pair is cached permanently.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from playwright.async_api import Page

from ..repository import Repository
from ..matching.normalize import compact, fold, normalize_position, normalize_rating
from ...models.schemas import PriceQuote
from ...models.tables import CatalogCard
from .base import PriceUnavailable
from .browser import BrowserPool, BrowserUnavailable, ChallengeNotCleared

logger = logging.getLogger(__name__)

GAME = "27"
BASE = "https://www.futwiz.com"
SEARCH_HOME = f"{BASE}/en/fc{GAME}/players"

_PRICE_RE = re.compile(r"^\d{1,3}(?:[,.]\d{3})+$|^\d{4,}$")

# Pull the platform prices out of the page. Platform is decided by the icon and
# label inside each block, not by colour, so a restyle does not break it.
# FUTWIZ renders 'Pricing unavailable at this time' where it has no PC data,
# which is a real answer and must be told apart from a failed read.
_PRICE_JS = r"""() => {
  const isPrice = (t) => /^\d{1,3}([,.]\d{3})+$/.test(t) || /^\d{4,}$/.test(t);
  const blocks = [...document.querySelectorAll('div.flex.flex-row.items-center')];
  const seen = [];
  for (const box of blocks) {
    const text = (box.innerText || '').trim();
    const leaves = [...box.querySelectorAll('*')].filter(e => !e.children.length);
    const priceEl = leaves.find(e => isPrice(e.textContent.trim()));
    const unavailable = /unavailable/i.test(text);
    if (!priceEl && !unavailable) continue;
    const icons = [...box.querySelectorAll('svg[data-icon]')].map(e => e.getAttribute('data-icon'));
    const ageEl = leaves.find(e => /(ago|min|hour|day|sec)/i.test(e.textContent));
    seen.push({
      price: priceEl ? priceEl.textContent.trim() : null,
      unavailable: unavailable,
      cls: priceEl ? (priceEl.className || '').toString() : '',
      icons: icons,
      hasPcLabel: leaves.some(e => e.textContent.trim() === 'PC'),
      age: ageEl ? ageEl.textContent.trim() : null,
      text: text.slice(0, 120)
    });
  }
  return seen;
}"""

_SEARCH_RESULTS_JS = """() => {
  const out = [];
  for (const a of document.querySelectorAll('a[href*="/player/"]')) {
    const href = a.getAttribute('href') || '';
    const m = href.match(/\\/fc(\\d+)\\/player\\/([a-z0-9-]+)\\/(\\d+)/i);
    if (!m) continue;
    const text = (a.innerText || '').replace(/\\s+/g, ' ').trim();
    out.push({ href, game: m[1], slug: m[2], id: parseInt(m[3], 10), text });
  }
  return out;
}"""

_CARD_ID_JS = """() => {
  const leaves = [...document.querySelectorAll('*')].filter(e => !e.children.length);
  const out = {};
  leaves.forEach((el, i) => {
    const label = el.textContent.trim();
    if (label !== 'Card ID' && label !== 'Player ID') return;
    for (let j = i + 1; j < Math.min(i + 6, leaves.length); j++) {
      const v = leaves[j].textContent.trim();
      if (/^\\d+$/.test(v)) { out[label] = parseInt(v, 10); break; }
    }
  });
  return out;
}"""


def _to_int(text: str) -> int | None:
    digits = re.sub(r"[^0-9]", "", text or "")
    return int(digits) if digits else None


class FutwizProvider:
    """Reads the PC lowest-BIN from FUTWIZ through a real browser."""

    name = "futwiz"
    platform = "pc"

    def __init__(self, pool: BrowserPool, repo: Repository) -> None:
        self._pool = pool
        self._repo = repo

    async def aclose(self) -> None:
        # The pool is shared and closed by the app, not by one provider.
        return None

    # -- public ------------------------------------------------------------
    async def fetch(self, card: CatalogCard) -> PriceQuote:
        futwiz_id, slug = await self._resolve_id(card)
        url = f"{BASE}/en/fc{GAME}/player/{slug}/{futwiz_id}"

        page = await self._open(url)
        try:
            await self._wait_for_prices(page)
            blocks = await page.evaluate(_PRICE_JS)
        finally:
            await self._pool.release(page)

        block = self._pc_block(blocks)
        if block is None:
            raise PriceUnavailable(
                self.name, "Sayfada PC fiyat blogu bulunamadi."
            )
        if block.get("unavailable"):
            # FUTWIZ says so itself; this is data, not a scraping failure.
            raise PriceUnavailable(
                self.name, "FUTWIZ bu kart icin PC fiyati yayinlamiyor."
            )

        pc_price = _to_int(block.get("price", ""))
        age = block.get("age")
        if pc_price is None:
            raise PriceUnavailable(self.name, "PC fiyati okunamadi.")

        return PriceQuote(
            ea_id=card.ea_id,
            price=pc_price,
            platform="pc",
            source=self.name,
            fetched_at=datetime.now(timezone.utc),
            is_extinct=pc_price == 0,
            note=f"FUTWIZ PC piyasasi - kaynakta: {age}" if age else "FUTWIZ PC piyasasi",
            source_url=url,
        )

    # -- internals ---------------------------------------------------------
    async def _open(self, url: str) -> Page:
        try:
            return await self._pool.open(url)
        except ChallengeNotCleared as exc:
            raise PriceUnavailable(self.name, f"Bot dogrulamasi gecilemedi: {exc}") from exc
        except BrowserUnavailable as exc:
            raise PriceUnavailable(self.name, str(exc)) from exc

    async def _wait_for_prices(self, page: Page) -> None:
        """Prices hydrate after load; give them a bounded window."""
        try:
            await page.wait_for_function(
                "() => [...document.querySelectorAll('*')].some(e => "
                "!e.children.length && /^\\d{1,3}([,.]\\d{3})+$/.test(e.textContent.trim()))",
                timeout=12_000,
            )
        except Exception:  # noqa: BLE001 - absence is a real answer, not an error
            logger.info("futwiz: fiyat dugumu 12 sn icinde gorunmedi")

    def _pick_pc(self, blocks: list[dict]) -> tuple[int | None, str | None]:
        """Choose the PC figure out of the platform price blocks."""
        block = self._pc_block(blocks)
        if block is None:
            return None, None
        return _to_int(block.get("price", "")), block.get("age")

    @staticmethod
    def _pc_block(blocks: list[dict]) -> dict | None:
        """The block FUTWIZ labels PC, by icon or label; colour as a last resort."""
        for block in blocks:
            if block.get("hasPcLabel") or "computer" in (block.get("icons") or []):
                return block
        for block in blocks:
            if "orange" in (block.get("cls") or ""):
                logger.info("futwiz: PC blogu renk sinifindan secildi")
                return block
        return None

    async def _resolve_id(self, card: CatalogCard) -> tuple[int, str]:
        """eaId -> FUTWIZ id, cached permanently after the first lookup."""
        cached = self._repo.futwiz_id(card.ea_id)
        if cached:
            return cached

        candidates = await self._search(card.name)
        if not candidates:
            raise PriceUnavailable(
                self.name, f"FUTWIZ aramasinda '{card.name}' bulunamadi."
            )

        shortlist = self._shortlist(candidates, card)
        if not shortlist:
            raise PriceUnavailable(
                self.name,
                f"FUTWIZ'de {card.name} icin {card.rating} {card.position} kart bulunamadi.",
            )

        for candidate in shortlist:
            url = f"{BASE}/en/fc{GAME}/player/{candidate['slug']}/{candidate['id']}"
            page = await self._open(url)
            try:
                ids = await page.evaluate(_CARD_ID_JS)
            finally:
                await self._pool.release(page)
            if ids.get("Card ID") == card.ea_id:
                self._repo.set_futwiz_id(card.ea_id, candidate["id"], candidate["slug"])
                logger.info(
                    "futwiz eslesme: eaId=%s -> futwizId=%s", card.ea_id, candidate["id"]
                )
                return candidate["id"], candidate["slug"]

        raise PriceUnavailable(
            self.name,
            f"FUTWIZ adaylarinin hicbirinin Card ID'si {card.ea_id} ile eslesmedi.",
        )

    async def _search(self, name: str) -> list[dict]:
        page = await self._open(SEARCH_HOME)
        try:
            box = page.locator('input[placeholder*="Search players" i]').first
            await box.wait_for(timeout=10_000)
            await box.click()
            await box.fill(name)
            await page.wait_for_timeout(2_500)
            return await page.evaluate(_SEARCH_RESULTS_JS)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            raise PriceUnavailable(
                self.name, f"FUTWIZ aramasi calistirilamadi: {type(exc).__name__}"
            ) from exc
        finally:
            await self._pool.release(page)

    def _shortlist(self, results: list[dict], card: CatalogCard) -> list[dict]:
        """Keep FC 27 results whose printed name/rating/position fit this card."""
        want_name = compact(card.name)
        out: list[dict] = []
        for result in results:
            if str(result.get("game")) != GAME:
                continue
            slug_name = compact(result.get("slug", "").replace("-", " "))
            text = result.get("text") or ""
            if want_name and want_name not in slug_name and slug_name not in want_name:
                if fold(card.name).split()[-1] not in fold(slug_name):
                    continue
            rating = self._rating_in(text)
            if card.rating is not None and rating is not None and rating != card.rating:
                continue
            position = self._position_in(text)
            if (
                card.position
                and position
                and position != card.position
                and position not in (card.alt_positions or [])
            ):
                continue
            out.append(result)
        return out

    @staticmethod
    def _rating_in(text: str) -> int | None:
        for token in re.findall(r"\b\d{1,2}\b", text):
            rating = normalize_rating(token)
            if rating is not None and rating >= 40:
                return rating
        return None

    @staticmethod
    def _position_in(text: str) -> str | None:
        for token in re.findall(r"\b[A-Z]{2,3}\b", text.upper()):
            position = normalize_position(token)
            if position:
                return position
        return None
