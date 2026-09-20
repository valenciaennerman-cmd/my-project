"""FUT.GG as the catalog / card-identity source.

Why FUT.GG and not FUTBIN: FUTBIN answers every non-browser request with a
Cloudflare interstitial (even /robots.txt), while FUT.GG server-renders its
player pages and publishes a sitemap. We use only paths that robots.txt allows
(`/players/...`, `/sitemap-*.xml`) and never the `/api/*` paths it disallows.

Prices are deliberately NOT read here -- FUT.GG only publishes console (`ps5`)
prices. See app/services/prices/ for the PC price path.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

import httpx

from ...models.tables import CatalogCard
from ..matching.normalize import fold, normalize_position, normalize_rating
from .serial import (
    enclosing_array,
    enclosing_object,
    meta_content,
    objects_in_array,
    scalar,
    string_list,
)

logger = logging.getLogger(__name__)

GAME = "27"
BASE = "https://www.fut.gg"
SITEMAP_FIRST = f"{BASE}/sitemap-player-detail-{GAME}.xml"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}

_URL_RE = re.compile(
    rf"{BASE}/players/(?P<base>\d+)-(?P<slug>[a-z0-9-]+)/{GAME}-(?P<ea>\d+)/"
)
_LOC_RE = re.compile(r"<loc>([^<]+)</loc>")


def card_url(base_player_ea_id: int, slug: str, ea_id: int) -> str:
    """Build a card URL from either slug convention.

    FUT.GG's `basePlayerSlug` already carries the id ("1397-zinedine-zidane"),
    while the sitemap path gives the bare name part ("zinedine-zidane"). Both
    turn up in this codebase, so both are accepted here rather than leaving the
    caller to remember which one it holds.
    """
    prefix = f"{base_player_ea_id}-"
    full = slug if slug.startswith(prefix) else f"{prefix}{slug}"
    return f"{BASE}/players/{full}/{GAME}-{ea_id}/"


class CatalogError(RuntimeError):
    """Catalog source could not be read. Always carries a usable message."""


@dataclass(slots=True)
class SitemapEntry:
    base_player_ea_id: int
    slug: str
    ea_id: int

    @property
    def url(self) -> str:
        return card_url(self.base_player_ea_id, self.slug, self.ea_id)

    @property
    def full_slug(self) -> str:
        """The slug shape FUT.GG uses internally, e.g. 1397-zinedine-zidane."""
        prefix = f"{self.base_player_ea_id}-"
        return self.slug if self.slug.startswith(prefix) else f"{prefix}{self.slug}"

    @property
    def name(self) -> str:
        return self.slug.replace("-", " ")


@dataclass(slots=True)
class CardPage:
    """Everything one player page tells us."""

    primary: CatalogCard
    siblings: list[CatalogCard]
    variant_ea_ids: list[int]


def parse_card_page(html: str, ea_id: int) -> CardPage:
    """Read a FUT.GG player page into cards.

    `primary` is the card the URL points at, `siblings` are the player's other
    versions listed on the page, and `variant_ea_ids` are its holographic
    siblings (which FUT.GG keeps out of the version list).
    """
    description = meta_content(html, "description") or ""
    common_name = _first_scalar(html, ea_id, "commonName") or ""
    version_label, rating, position = _split_description(description, common_name)

    base_player = _first_scalar(html, ea_id, "basePlayerEaId")
    slug = _first_scalar(html, ea_id, "basePlayerSlug") or ""
    if not base_player:
        match = _URL_RE.search(html)
        base_player = int(match.group("base")) if match else ea_id
        slug = slug or (match.group("slug") if match else "")

    alt_positions = _alt_positions(html, ea_id)
    holographic = _first_scalar(html, ea_id, "holographicType")
    if holographic and version_label and "holo" not in fold(version_label):
        version_label = f"{version_label} {holographic.title()} Holographic".strip()

    primary = CatalogCard(
        ea_id=ea_id,
        base_player_ea_id=int(base_player),
        name=common_name or slug.replace("-", " "),
        slug=slug,
        url=card_url(int(base_player), slug, ea_id),
        rating=rating,
        position=position,
        alt_positions=alt_positions,
        rarity_name=_first_scalar(html, ea_id, "rarityName"),
        version_label=version_label,
        image_url=_card_image(html, ea_id),
    )

    return CardPage(
        primary=primary,
        siblings=_current_versions(html, exclude=ea_id),
        variant_ea_ids=_item_variants(html, exclude=ea_id),
    )


def _first_scalar(html: str, ea_id: int, key: str) -> object:
    """Find `key` in any serialized object that names this eaId."""
    for match in re.finditer(rf"eaId:{ea_id}(?![0-9])", html):
        block = enclosing_object(html, match.start())
        if not block:
            continue
        value = scalar(block, key)
        if value is not None:
            return value
    return None


def _alt_positions(html: str, ea_id: int) -> list[str]:
    for match in re.finditer(rf"eaId:{ea_id}(?![0-9])", html):
        block = enclosing_object(html, match.start())
        if not block:
            continue
        found = string_list(block, "alternativePositions")
        if found:
            return [p for p in (normalize_position(x) for x in found) if p]
    return []


# Only these asset folders hold the rendered card; `imageUrl` on a block can
# just as easily be a nation flag or club badge.
_CARD_IMAGE_MARKERS = ("player-item", "futgg-player-item-card")


def _card_image(html: str, ea_id: int) -> str | None:
    blocks = [
        block
        for match in re.finditer(rf"eaId:{ea_id}(?![0-9])", html)
        if (block := enclosing_object(html, match.start()))
    ]
    for key in ("cardImageUrl", "simpleCardImageUrl", "socialImageUrl"):
        for block in blocks:
            url = scalar(block, key)
            if isinstance(url, str) and url.startswith("http"):
                return url
    # Fall back to the page's own social image, which is card-specific.
    og = meta_content(html, "og:image")
    if og and any(marker in og for marker in _CARD_IMAGE_MARKERS):
        return og
    for block in blocks:
        url = scalar(block, "imageUrl")
        if isinstance(url, str) and any(m in url for m in _CARD_IMAGE_MARKERS):
            return url
    return og


def _split_description(description: str, common_name: str) -> tuple[str | None, int | None, str | None]:
    """'Zinedine Zidane Base Icon Pristine Holographic 94 OVR CAM (ICON) on ...'

    -> ('Base Icon Pristine Holographic', 94, 'CAM')

    The version label is the only field that spells out 'Holographic', which the
    Zidane test showed is what separates otherwise identical cards.
    """
    if not description:
        return None, None, None
    head = description.split(" on EA FC")[0].strip()

    if common_name and head.lower().startswith(common_name.lower()):
        head = head[len(common_name) :].strip()

    match = re.search(r"^(?P<version>.*?)\s*(?P<rating>\d{1,2})\s+OVR\s+(?P<pos>[A-Z]{2,3})", head)
    if not match:
        return (head or None), None, None
    version = match.group("version").strip(" -–") or None
    return version, normalize_rating(match.group("rating")), normalize_position(match.group("pos"))


def _current_versions(html: str, exclude: int) -> list[CatalogCard]:
    """The player's other card versions, as listed on the page."""
    match = re.search(r"currentVersions:(?:\$R\[\d+\]=)?\[", html)
    if not match:
        return []
    array = enclosing_array(html, match.end() - 1)
    if not array:
        return []

    out: list[CatalogCard] = []
    for block in objects_in_array(array):
        ea = scalar(block, "eaId")
        overall = scalar(block, "overall")
        if not isinstance(ea, int) or ea == exclude or not isinstance(overall, int):
            continue
        slug = scalar(block, "basePlayerSlug") or ""
        base = scalar(block, "basePlayerEaId") or 0
        image = scalar(block, "cardImageUrl") or scalar(block, "simpleCardImageUrl")
        rarity = scalar(block, "rarityName")
        holo = scalar(block, "holographicType")
        label = rarity
        if holo and rarity:
            label = f"{rarity} {str(holo).title()} Holographic"
        out.append(
            CatalogCard(
                ea_id=ea,
                base_player_ea_id=int(base),
                name=str(scalar(block, "commonName") or scalar(block, "cardName") or ""),
                slug=str(slug),
                url=f"{BASE}{scalar(block, 'url') or ''}",
                rating=normalize_rating(overall),
                position=normalize_position(scalar(block, "position")),
                alt_positions=[
                    p for p in (normalize_position(x) for x in string_list(block, "alternativePositions")) if p
                ],
                rarity_name=rarity,
                version_label=label,
                image_url=image if isinstance(image, str) else None,
            )
        )
    return out


def _item_variants(html: str, exclude: int) -> list[int]:
    """Holographic siblings of this exact card, e.g. [1397, 100664693]."""
    match = re.search(r"itemVariants:(?:\$R\[\d+\]=)?\[", html)
    if not match:
        return []
    array = enclosing_array(html, match.end() - 1)
    if not array:
        return []
    out = []
    for block in objects_in_array(array):
        ea = scalar(block, "eaId")
        if isinstance(ea, int) and ea != exclude:
            out.append(ea)
    return out


class FutGGCatalog:
    """HTTP client for the FUT.GG catalog. Plain requests -- no browser needed."""

    def __init__(
        self,
        timeout: float = 20.0,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
        page_delay: float = 0.4,
        max_pages: int = 60,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        # Injectable so tests do not have to wait, and so the crawl pace
        # stays tunable in one place.
        self._retry_backoff = retry_backoff
        self._page_delay = page_delay
        self._max_pages = max_pages
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> FutGGCatalog:
        self._client = httpx.AsyncClient(
            headers=HEADERS, timeout=self._timeout, follow_redirects=True
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get(self, url: str) -> str:
        if self._client is None:
            raise CatalogError("Katalog istemcisi baslatilmadi.")
        delay = self._retry_backoff
        last: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.get(url)
                if response.status_code == 200:
                    return response.text
                if response.status_code in (429, 500, 502, 503, 504):
                    last = CatalogError(f"{url} -> HTTP {response.status_code}")
                    logger.warning(
                        "fut.gg %s -> %s (deneme %d/%d)",
                        url, response.status_code, attempt, self._max_retries,
                    )
                else:
                    raise CatalogError(f"{url} -> HTTP {response.status_code}")
            except httpx.HTTPError as exc:
                last = exc
                logger.warning("fut.gg %s hata: %s (deneme %d)", url, exc, attempt)
            if attempt < self._max_retries:
                if delay > 0:
                    await asyncio.sleep(delay)
                delay *= 2
        raise CatalogError(f"{url} okunamadi: {last}")

    async def sitemap_entries(self) -> list[SitemapEntry]:
        """Every FC 27 card URL, from the sitemap FUT.GG publishes for crawlers.

        Stops on an empty page, on a page that adds nothing new, or at
        `max_pages` -- a server that keeps answering with the same page must not
        turn this into an endless crawl.
        """
        entries: list[SitemapEntry] = []
        seen: set[int] = set()

        for page in range(1, self._max_pages + 1):
            url = SITEMAP_FIRST if page == 1 else f"{SITEMAP_FIRST}?p={page}"
            try:
                body = await self._get(url)
            except CatalogError:
                if page == 1:
                    raise
                break

            locs = _LOC_RE.findall(body)
            if not locs:
                break

            new_on_page = 0
            for loc in locs:
                match = _URL_RE.match(loc)
                if not match:
                    continue
                ea_id = int(match.group("ea"))
                if ea_id in seen:
                    continue
                seen.add(ea_id)
                new_on_page += 1
                entries.append(
                    SitemapEntry(
                        base_player_ea_id=int(match.group("base")),
                        slug=match.group("slug"),
                        ea_id=ea_id,
                    )
                )

            logger.info(
                "sitemap sayfa %d: %d URL, %d yeni (toplam %d)",
                page, len(locs), new_on_page, len(entries),
            )
            if new_on_page == 0:
                logger.info("sayfa %d yeni kart getirmedi, duruluyor", page)
                break

            if self._page_delay > 0:
                await asyncio.sleep(self._page_delay)  # be a polite crawler
        else:
            logger.warning(
                "sitemap %d sayfada kesildi; kaynak beklenenden fazla sayfa donuyor",
                self._max_pages,
            )
        return entries

    async def card_page(self, url: str, ea_id: int) -> CardPage:
        return parse_card_page(await self._get(url), ea_id)
