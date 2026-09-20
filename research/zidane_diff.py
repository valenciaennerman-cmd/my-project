"""Zidane test: for each FC 27 Zidane card URL, extract every field we can and
report which fields actually differ between the cards.

Proves with data (not assumption) which field identifies a card *version*.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any

sys.path.insert(0, "research")
from futgg_parse import enclosing_object, _scalar, _meta  # noqa: E402

CARD_KEYS = (
    "id", "overall", "commonName", "cardName", "rarityName", "raritySquadId",
    "textColor", "lineColor", "overallColor", "dominantColor", "url",
    "isSpecial", "isDynamic", "isSbc", "isObjective", "isIcon", "isHero",
    "position", "positionId", "foot", "weakFoot", "skillMoves", "createdAt",
    "nationEaId", "leagueEaId", "clubEaId", "rarityEaId", "basePlayerEaId",
    "height", "age", "hasPrice", "gradingScore", "evolutionId",
    "rarityImageUrl", "socialImagePath",
)

PAGES = {
    1397: "research/futgg_zidane_1397.html",
    100664693: "research/futgg_zidane_100664693.html",
    67110261: "research/futgg_zidane_67110261.html",
    83887477: "research/futgg_zidane_83887477.html",
}


def card_for(html: str, ea_id: int) -> dict[str, Any]:
    """Union the fields of every serialized object that names this eaId."""
    rec: dict[str, Any] = {"eaId": ea_id}
    for match in re.finditer(rf"eaId:{ea_id}(?![0-9])", html):
        block = enclosing_object(html, match.start())
        if not block:
            continue
        for key in CARD_KEYS:
            if rec.get(key) is None:
                value = _scalar(block, key)
                if value is not None and not (
                    isinstance(value, str) and value.startswith("$R[")
                ):
                    rec[key] = value
        if rec.get("alternativePositions") is None:
            alt = re.search(
                r"alternativePositions:(?:\$R\[\d+\]=)?\[([^\]]*)\]", block
            )
            if alt:
                rec["alternativePositions"] = re.findall(r'"([^"]+)"', alt.group(1))
    return rec


def main() -> None:
    print("=" * 100)
    print("PAGE-LEVEL IDENTITY  (read straight off each URL, plain requests, no JS)")
    print("=" * 100)
    cards: dict[int, dict[str, Any]] = {}
    for ea, path in PAGES.items():
        html = open(path, encoding="utf-8", errors="replace").read()
        rec = card_for(html, ea)
        rec["meta_description"] = (_meta(html, "description") or "").split(" on EA FC 27")[0]
        rec["html_title"] = re.search(r"<title>([^<]*)</title>", html).group(1)
        rec["og_image"] = _meta(html, "og:image")
        cards[ea] = rec
        print(f"\n-- /players/1397-zinedine-zidane/27-{ea}/")
        print(f"   title : {rec['html_title']}")
        print(f"   ident : {rec['meta_description']}")

    print("\n" + "=" * 100)
    print("FIELD-BY-FIELD ACROSS THE 4 CARDS")
    print("=" * 100)
    keys = sorted({k for r in cards.values() for k in r})
    differing: list[tuple[str, list[str]]] = []
    identical: list[str] = []
    for key in keys:
        vals = [
            json.dumps(cards[ea].get(key), ensure_ascii=False, sort_keys=True)
            for ea in PAGES
        ]
        (differing.append((key, vals)) if len(set(vals)) > 1 else identical.append(key))

    print(f"\nDIFFERENT ({len(differing)}) -- candidates for telling versions apart:\n")
    header = "  " + "field".ljust(20) + "".join(str(e).ljust(30) for e in PAGES)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for key, vals in differing:
        cells = "".join((v[:28] + "..") if len(v) > 29 else v.ljust(30) for v in vals)
        print("  " + key.ljust(20) + cells)

    print(f"\nIDENTICAL ({len(identical)}) -- carry no disambiguating signal:\n")
    print("  " + ", ".join(identical))

    print("\n" + "=" * 100)
    print("THE HARD PAIRS  (same name + same rating + same position)")
    print("=" * 100)
    for a, b in ((1397, 100664693), (67110261, 83887477)):
        ra, rb = cards[a], cards[b]
        print(f"\n  {a}  vs  {b}")
        for key in ("commonName", "overall", "position", "alternativePositions",
                    "clubEaId", "nationEaId", "leagueEaId"):
            mark = "SAME" if ra.get(key) == rb.get(key) else "DIFF"
            print(f"      {mark}  {key:22} {ra.get(key)!r} / {rb.get(key)!r}")
        for key in ("rarityName", "rarityEaId", "raritySquadId", "meta_description"):
            mark = "SAME" if ra.get(key) == rb.get(key) else "DIFF"
            print(f"      {mark}  {key:22} {str(ra.get(key))[:44]!r} / {str(rb.get(key))[:44]!r}")


if __name__ == "__main__":
    main()
