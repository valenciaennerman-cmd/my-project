"""Extract card fields from a FUT.GG player detail page (server-rendered HTML).

Used for the pre-build research spike: prove that every field needed to tell two
cards of the same player apart is present in a plain `requests` response.
"""
from __future__ import annotations

import json
import re
from typing import Any

BACKSLASH = chr(92)
QUOTE = chr(34)


def enclosing_object(text: str, pos: int) -> str | None:
    """Return the brace-balanced ``{...}`` literal that contains ``pos``."""
    start = text.rfind("{", 0, pos)
    while start >= 0:
        depth = 0
        in_string = False
        escaped = False
        idx = start
        while idx < len(text):
            ch = text[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == BACKSLASH:
                    escaped = True
                elif ch == QUOTE:
                    in_string = False
            elif ch == QUOTE:
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    if idx > pos:
                        return text[start : idx + 1]
                    break
            idx += 1
        start = text.rfind("{", 0, start)
    return None


def _scalar(block: str, key: str) -> Any:
    """Read one ``key:value`` scalar out of the serialized object literal."""
    m = re.search(rf"(?<![A-Za-z0-9_]){re.escape(key)}:", block)
    if not m:
        return None
    raw = block[m.end() :]
    if raw.startswith(QUOTE):
        end = 1
        while end < len(raw):
            if raw[end] == BACKSLASH:
                end += 2
                continue
            if raw[end] == QUOTE:
                break
            end += 1
        return raw[1:end]
    value = re.match(r"[^,}\]]*", raw).group(0).strip()
    if value == "!0":
        return True
    if value == "!1":
        return False
    if value in ("null", "void 0", "undefined"):
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value or None


def _meta(html: str, prop: str) -> str | None:
    m = re.search(
        rf'<meta[^>]+(?:name|property)="{re.escape(prop)}"[^>]+content="([^"]*)"',
        html,
    )
    if m:
        return m.group(1)
    m = re.search(
        rf'<meta[^>]+content="([^"]*)"[^>]+(?:name|property)="{re.escape(prop)}"',
        html,
    )
    return m.group(1) if m else None


def parse_player_page(html: str, ea_id: int) -> dict[str, Any]:
    """Pull the identity + price fields for ``ea_id`` out of a FUT.GG page."""
    out: dict[str, Any] = {"eaId": ea_id}

    match = re.search(rf"eaId:{ea_id}(?![0-9])", html)
    block = enclosing_object(html, match.start()) if match else None
    out["_block_found"] = block is not None
    out["_block_len"] = len(block) if block else 0

    if block:
        for key in (
            "eaId", "basePlayerEaId", "commonName", "firstName", "lastName",
            "overall", "position", "rarityName", "raritySquadId",
            "isIcon", "isHero", "isSpecial", "isSbc", "isObjective", "isDynamic",
            "hasPrice", "price", "url", "foot", "weakFoot", "skillMoves",
            "rarityImageUrl", "socialImagePath", "nationEaId", "leagueEaId",
            "clubEaId", "isBrightColorScheme", "textColor", "lineColor",
        ):
            out[key] = _scalar(block, key)
        alt = re.search(r"alternativePositions:(?:\$R\[\d+\]=)?\[([^\]]*)\]", block)
        if alt:
            out["alternativePositions"] = re.findall(r'"([^"]+)"', alt.group(1))

    out["meta_description"] = _meta(html, "description")
    out["og_title"] = _meta(html, "og:title")
    out["og_image"] = _meta(html, "og:image")
    title = re.search(r"<title>([^<]*)</title>", html)
    out["html_title"] = title.group(1) if title else None

    # Price block rendered into the page body (Lowest BIN / momentum).
    out["visible_prices"] = re.findall(
        r"<[^>]*>([0-9]{1,3}(?:[.,][0-9]{3})+)<", html
    )[:12]
    out["extinct_flag"] = "EXTINCT" in html.upper()
    return out


if __name__ == "__main__":
    import sys

    path, ea = sys.argv[1], int(sys.argv[2])
    data = parse_player_page(
        open(path, encoding="utf-8", errors="replace").read(), ea
    )
    print(json.dumps(data, indent=2, ensure_ascii=False))
