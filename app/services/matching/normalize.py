"""Name normalisation.

Card screenshots render names with accents and Turkish-specific letters, and the
catalog slugs are plain ASCII. Everything is folded to a common form before it
is compared or fuzzy-matched.
"""
from __future__ import annotations

import re
import unicodedata

# Characters NFKD does not decompose the way we need, plus Turkish specials.
_SPECIAL: dict[str, str] = {
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ç": "c", "Ç": "c", "ö": "o", "Ö": "o", "ü": "u", "Ü": "u",
    "ø": "o", "Ø": "o", "ð": "d", "Ð": "d", "þ": "th", "Þ": "th",
    "ß": "ss", "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe",
    "ł": "l", "Ł": "l", "đ": "d", "Đ": "d", "ŋ": "n", "ʼ": "'",
}

_WHITESPACE = re.compile(r"\s+")
_NON_NAME = re.compile(r"[^a-z0-9' -]")

POSITION_ALIASES: dict[str, str] = {
    "GK": "GK", "CB": "CB", "LB": "LB", "RB": "RB", "LWB": "LWB", "RWB": "RWB",
    "CDM": "CDM", "CM": "CM", "CAM": "CAM", "LM": "LM", "RM": "RM",
    "LW": "LW", "RW": "RW", "CF": "CF", "ST": "ST",
    # Things OCR/vision commonly emits for the same slot.
    "GOALKEEPER": "GK", "STRIKER": "ST", "CENTER BACK": "CB",
    "CENTRE BACK": "CB", "LEFT BACK": "LB", "RIGHT BACK": "RB",
    "DEFENSIVE MIDFIELDER": "CDM", "ATTACKING MIDFIELDER": "CAM",
    "CENTRAL MIDFIELDER": "CM", "LEFT WING": "LW", "RIGHT WING": "RW",
    "LEFT MIDFIELD": "LM", "RIGHT MIDFIELD": "RM",
}

VALID_POSITIONS = frozenset(
    {"GK", "CB", "LB", "RB", "LWB", "RWB", "CDM", "CM", "CAM",
     "LM", "RM", "LW", "RW", "CF", "ST"}
)


def fold(text: str) -> str:
    """Lowercase, strip accents and punctuation noise. 'Martí' -> 'marti'."""
    if not text:
        return ""
    for src, dst in _SPECIAL.items():
        text = text.replace(src, dst)
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = stripped.lower().replace("_", " ").replace(".", " ")
    cleaned = _NON_NAME.sub(" ", lowered)
    return _WHITESPACE.sub(" ", cleaned).strip()


def compact(text: str) -> str:
    """Fold, then drop every separator. 'Kika Nazareth' -> 'kikanazareth'.

    Useful because OCR and card art both like to glue names together.
    """
    return re.sub(r"[^a-z0-9]", "", fold(text))


def slug_to_name(slug: str) -> str:
    """'1397-zinedine-zidane' -> 'zinedine zidane'."""
    body = slug.split("-", 1)[1] if "-" in slug and slug.split("-", 1)[0].isdigit() else slug
    return fold(body.replace("-", " "))


def surname(text: str) -> str:
    """Last token of a folded name; cards usually print only this."""
    parts = fold(text).split()
    return parts[-1] if parts else ""


def normalize_position(value: str | None) -> str | None:
    """Map whatever the reader produced onto a real FC position, or None."""
    if not value:
        return None
    raw = re.sub(r"[^A-Za-z ]", "", str(value)).strip().upper()
    if not raw:
        return None
    if raw in POSITION_ALIASES:
        return POSITION_ALIASES[raw]
    squeezed = raw.replace(" ", "")
    if squeezed in VALID_POSITIONS:
        return squeezed
    return POSITION_ALIASES.get(squeezed)


def normalize_rating(value: object) -> int | None:
    """Ratings in FC run 1-99. Anything outside that is a misread."""
    try:
        rating = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return rating if 1 <= rating <= 99 else None
