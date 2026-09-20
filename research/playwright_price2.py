"""Does the FUT.GG price actually hydrate under headless Chromium?

Logs the signed price request/response so the answer is evidence, not a guess.
"""
from __future__ import annotations

import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

URL = "https://www.fut.gg/players/231747-kylian-mbappe/27-231747/"


def probe(headless: bool) -> None:
    print("=" * 84)
    print(f"headless={headless}")
    print("=" * 84)
    seen: list[str] = []
    bodies: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        page = ctx.new_page()

        def on_response(resp):
            if "price" not in resp.url:
                return
            seen.append(f"{resp.status} {resp.request.method} {resp.url[:110]}")
            if "player-prices" in resp.url:
                try:
                    bodies.append(resp.text()[:400])
                except Exception as exc:  # noqa: BLE001
                    bodies.append(f"<body unavailable: {type(exc).__name__}>")

        page.on("response", on_response)

        started = time.perf_counter()
        page.goto(URL, wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(6_000)
        elapsed = time.perf_counter() - started

        body = page.inner_text("body")
        inline = re.search(r"\nPrice:\s*\n([^\n]+)", body)
        lowest = re.search(r"Lowest BIN\s*\n([^\n]+)\n([^\n]+)\n([^\n]+)", body)

        print(f"  load+settle: {elapsed:.1f}s")
        print(f"  price requests seen: {len(seen)}")
        for line in seen:
            print(f"    {line}")
        for b in bodies:
            print(f"  RESPONSE BODY: {b}")
        print(f"  inline 'Price:' -> {inline.group(1).strip() if inline else None!r}")
        print(f"  'Lowest BIN' block -> {[g.strip() for g in lowest.groups()] if lowest else None}")
        browser.close()


if __name__ == "__main__":
    probe(headless=(sys.argv[1] != "headful" if len(sys.argv) > 1 else True))
