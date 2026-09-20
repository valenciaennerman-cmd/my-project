"""Reader for the JS-literal state FUT.GG server-renders into its pages.

The page embeds objects like `$R[12]={eaId:1397,overall:94,isIcon:!0,...}`.
It is not JSON (`!0`/`!1` booleans, unquoted keys, `$R[n]=` back-references), so
it is read key-by-key rather than parsed wholesale. That keeps us tolerant of
fields being added or reordered upstream.
"""
from __future__ import annotations

import re
from typing import Any

BACKSLASH = chr(92)
QUOTE = chr(34)


def enclosing_object(text: str, pos: int) -> str | None:
    """Return the brace-balanced `{...}` literal containing `pos`."""
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


def enclosing_array(text: str, pos: int) -> str | None:
    """Return the bracket-balanced `[...]` literal starting at/after `pos`.

    Skips the `$R[12]=` back-reference prefix that precedes most arrays.
    """
    start = text.find("[", pos)
    while start >= 0:
        # `$R[12]` is a reference, not the array we want.
        if text[max(0, start - 3) : start] == "$R[" or (
            start >= 2 and text[start - 2 : start] == "$R"
        ):
            start = text.find("[", start + 1)
            continue
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
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]
            idx += 1
        return None
    return None


def scalar(block: str, key: str) -> Any:
    """Read one `key:value` scalar out of an object literal."""
    match = re.search(rf"(?<![A-Za-z0-9_]){re.escape(key)}:", block)
    if not match:
        return None
    raw = block[match.end() :]

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
    if value in ("null", "void 0", "undefined", ""):
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if value.startswith("$R["):
        return None
    return value


def string_list(block: str, key: str) -> list[str]:
    """Read `key:["CM","LW"]`, tolerating a `$R[n]=` prefix."""
    match = re.search(rf"{re.escape(key)}:(?:\$R\[\d+\]=)?\[([^\]]*)\]", block)
    return re.findall(rf'{QUOTE}([^{QUOTE}]+){QUOTE}', match.group(1)) if match else []


def objects_in_array(array_text: str) -> list[str]:
    """Split an array literal into its top-level `{...}` elements."""
    out: list[str] = []
    cursor = 0
    while True:
        brace = array_text.find("{", cursor)
        if brace < 0:
            return out
        obj = enclosing_object(array_text, brace + 1)
        if not obj:
            return out
        out.append(obj)
        cursor = array_text.find(obj, cursor) + len(obj)


def meta_content(html: str, prop: str) -> str | None:
    """Read a `<meta name=... content=...>` value in either attribute order."""
    escaped = re.escape(prop)
    match = re.search(
        rf'<meta[^>]+(?:name|property)="{escaped}"[^>]+content="([^"]*)"', html
    )
    if match:
        return match.group(1)
    match = re.search(
        rf'<meta[^>]+content="([^"]*)"[^>]+(?:name|property)="{escaped}"', html
    )
    return match.group(1) if match else None
