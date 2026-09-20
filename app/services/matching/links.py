"""Parse pasted card links into the id that identifies the card version.

The three sites number cards differently:
  fut.gg   /players/{basePlayerEaId}-{slug}/27-{eaId}/   -> EA item id (canonical)
  futwiz   /en/fc27/player/{slug}/{futwizId}             -> FUTWIZ's own id
  futbin   /27/player/{futbinId}/{slug}                  -> FUTBIN's own id

Only the fut.gg form yields the canonical EA id directly. FUTWIZ pages print
their EA "Card ID", so a FUTWIZ link is resolvable with one page fetch. FUTBIN
is unreachable (Cloudflare), so those links are recognised and reported as such
rather than silently failing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

LinkKind = Literal["futgg", "futwiz", "futbin"]

_FUTGG = re.compile(
    r"fut\.gg/players/(?P<base>\d+)-(?P<slug>[a-z0-9-]+)/(?P<game>\d+)-(?P<ea>\d+)",
    re.IGNORECASE,
)
_FUTWIZ = re.compile(
    r"futwiz\.com/(?:[a-z]{2}/)?fc(?P<game>\d+)/player/(?P<slug>[a-z0-9-]+)/(?P<id>\d+)",
    re.IGNORECASE,
)
_FUTBIN = re.compile(
    r"futbin\.com/(?P<game>\d+)/player/(?P<id>\d+)(?:/(?P<slug>[a-z0-9-]+))?",
    re.IGNORECASE,
)


class LinkError(ValueError):
    """The pasted text is not a card link we can act on."""


@dataclass(frozen=True, slots=True)
class ParsedLink:
    kind: LinkKind
    site_id: int
    slug: str | None = None
    ea_id: int | None = None
    base_player_ea_id: int | None = None
    game: str | None = None

    @property
    def resolvable(self) -> bool:
        """Can this link be turned into a card without hitting a blocked site?"""
        return self.kind in ("futgg", "futwiz")


def parse_card_link(text: str) -> ParsedLink:
    """Extract the card id from a pasted URL.

    Raises LinkError with a message meant for the user, never a bare failure.
    """
    if not text or not text.strip():
        raise LinkError("Link bos.")
    candidate = text.strip()

    match = _FUTGG.search(candidate)
    if match:
        return ParsedLink(
            kind="futgg",
            site_id=int(match.group("ea")),
            slug=match.group("slug"),
            ea_id=int(match.group("ea")),
            base_player_ea_id=int(match.group("base")),
            game=match.group("game"),
        )

    match = _FUTWIZ.search(candidate)
    if match:
        return ParsedLink(
            kind="futwiz",
            site_id=int(match.group("id")),
            slug=match.group("slug"),
            game=match.group("game"),
        )

    match = _FUTBIN.search(candidate)
    if match:
        return ParsedLink(
            kind="futbin",
            site_id=int(match.group("id")),
            slug=match.group("slug"),
            game=match.group("game"),
        )

    raise LinkError(
        "Taninmayan link. FUT.GG veya FUTWIZ kart linki yapistir "
        "(orn. https://www.fut.gg/players/1397-zinedine-zidane/27-100664693/)."
    )


def futgg_card_url(base_player_ea_id: int, slug: str, ea_id: int, game: str = "27") -> str:
    return f"https://www.fut.gg/players/{base_player_ea_id}-{slug}/{game}-{ea_id}/"


def futwiz_card_url(slug: str, futwiz_id: int, game: str = "27") -> str:
    return f"https://www.futwiz.com/en/fc{game}/player/{slug}/{futwiz_id}"
