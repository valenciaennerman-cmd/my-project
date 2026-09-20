"""Turn a card reading into catalog candidates.

Strategy, in order of trust:
  1. name  -> which *player* is this (fuzzy, accent-folded)
  2. rating -> which of that player's cards (exact; the reader is reliable here)
  3. position -> tie-break, accepting alternative positions
  4. card style -> last-resort ranking hint only

Deliberately never auto-picks between two cards that agree on all of the above:
the Zidane test showed such pairs exist and differ only in artwork, so the user
picks. See research/FINDINGS.md.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from ...models.schemas import CardReading
from ...models.tables import CatalogCard
from .normalize import compact, fold, surname

logger = logging.getLogger(__name__)

# Below this, we treat the name as "not found" rather than guessing.
NAME_SCORE_FLOOR = 78.0


@dataclass(slots=True)
class PlayerHit:
    base_player_ea_id: int
    slug: str
    name: str
    score: float


def match_player(
    query: str, index: dict[str, tuple[int, str]], limit: int = 6
) -> list[PlayerHit]:
    """Fuzzy-match a printed name against the catalog's player index.

    `index` maps folded player name -> (base_player_ea_id, slug).
    Cards usually print only the surname, so surname matches count too.
    """
    folded = fold(query)
    if not folded or not index:
        return []

    keys = list(index)
    hits: dict[str, float] = {}

    for key, score, _ in process.extract(
        folded, keys, scorer=fuzz.WRatio, limit=limit * 3
    ):
        hits[key] = max(hits.get(key, 0.0), float(score))

    # A card printing "Zidane" should still reach "zinedine zidane".
    last = surname(query)
    if last and last != folded:
        for key, score, _ in process.extract(
            last, keys, scorer=fuzz.WRatio, limit=limit * 3
        ):
            # Only credit it if the surname really is a token of that name.
            if last in key.split() or compact(last) in compact(key):
                hits[key] = max(hits.get(key, 0.0), float(score))

    # OCR/art glues names together ("kikanazareth").
    squashed = compact(query)
    if squashed:
        for key in keys:
            if compact(key) == squashed:
                hits[key] = max(hits.get(key, 0.0), 100.0)

    ranked = sorted(hits.items(), key=lambda kv: -kv[1])
    out: list[PlayerHit] = []
    for key, score in ranked:
        if score < NAME_SCORE_FLOOR:
            continue
        base_id, slug = index[key]
        out.append(PlayerHit(base_player_ea_id=base_id, slug=slug, name=key, score=score))
        if len(out) >= limit:
            break
    return out


def filter_cards(cards: list[CatalogCard], reading: CardReading) -> list[CatalogCard]:
    """Narrow one player's cards down using rating, then position."""
    pool = list(cards)

    if reading.rating is not None and any(c.rating is not None for c in pool):
        exact = [c for c in pool if c.rating == reading.rating]
        if exact:
            pool = exact
        else:
            # Tolerate a one-off misread, but no further: a reading of 6 against
            # a 94 card is a bad read, and showing that card as a confident
            # match would be worse than reporting no match at all.
            near = [
                c for c in pool
                if c.rating is not None and abs(c.rating - reading.rating) <= 1
            ]
            if not near:
                logger.info(
                    "okunan rating %s bu oyuncunun hicbir kartina uymuyor (%s)",
                    reading.rating, sorted({c.rating for c in pool if c.rating}),
                )
                return []
            logger.info(
                "rating %s birebir yok; +/-1 ile %d kart", reading.rating, len(near)
            )
            pool = near

    if reading.position and len(pool) > 1:
        want = reading.position
        primary = [c for c in pool if c.position == want]
        if primary:
            pool = primary
        else:
            alt = [c for c in pool if want in (c.alt_positions or [])]
            if alt:
                pool = alt

    return pool


def rank_by_style(cards: list[CatalogCard], reading: CardReading) -> list[CatalogCard]:
    """Order candidates by how well their version label fits the seen artwork.

    A ranking hint for the picker only -- it never drops a candidate, because
    artwork words ('holographic', 'icon') are not reliable enough to decide.
    """
    hint = fold(
        " ".join(filter(None, [reading.card_type, reading.card_style_description]))
    )
    if not hint:
        return cards

    def score(card: CatalogCard) -> float:
        label = fold(card.display_version)
        if not label:
            return 0.0
        base = float(fuzz.token_set_ratio(hint, label))
        # "holographic" is the discriminator that separates look-alike cards.
        holo_seen = "holo" in hint or "pembe" in hint or "pink" in hint
        holo_card = "holo" in label
        if holo_seen == holo_card:
            base += 25.0
        return base

    return sorted(cards, key=score, reverse=True)
