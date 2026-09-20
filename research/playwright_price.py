"""Measure what a real browser can get that plain `requests` cannot.

Two questions:
  1. Does Playwright get past FUTBIN's Cloudflare challenge?
  2. How fast/reliable is reading a FUT.GG price from the rendered page?
"""
from __future__ import annotations

import json
import re
import time

from playwright.sync_api import sync_playwright

FUTGG_CARDS = [
    ("Mbappé 91 Rare", "https://www.fut.gg/players/231747-kylian-mbappe/27-231747/"),
    ("Zidane 94 Base Icon", "https://www.fut.gg/players/1397-zinedine-zidane/27-1397/"),
    ("Zidane 94 Pristine Holo", "https://www.fut.gg/players/1397-zinedine-zidane/27-100664693/"),
    ("Messi 27-158023", "https://www.fut.gg/players/158023-lionel-messi/27-158023/"),
]
FUTBIN_URL = "https://www.futbin.com/27/player/21491/zidane"


def read_futgg_price(page, url: str) -> dict[str, object]:
    started = time.perf_counter()
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    price_text = None
    try:
        # The price block hydrates after the signed /api/ call resolves.
        page.wait_for_function(
            """() => {
                const el = [...document.querySelectorAll('*')]
                  .find(e => e.children.length === 0 && /^(Extinct|[0-9][0-9.,]{2,})$/.test(e.textContent.trim()));
                return !!el;
            }""",
            timeout=20_000,
        )
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        return {"ok": False, "reason": f"{type(exc).__name__}", "seconds": time.perf_counter() - started}

    body = page.inner_text("body")
    m = re.search(r"Lowest BIN\s*\n([^\n]*)\n([^\n]*)", body)
    if m:
        price_text = f"{m.group(1).strip()} / {m.group(2).strip()}"
    m2 = re.search(r"\nPrice:\s*\n([^\n]+)", body)
    inline = m2.group(1).strip() if m2 else None
    title = page.title()
    return {
        "ok": True,
        "seconds": time.perf_counter() - started,
        "title": title,
        "lowest_bin_block": price_text,
        "inline_price": inline,
    }


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = ctx.new_page()

        print("=" * 84)
        print("FUT.GG via Playwright (headless chromium)")
        print("=" * 84)
        for label, url in FUTGG_CARDS:
            res = read_futgg_price(page, url)
            print(f"\n  {label}")
            print(f"    {json.dumps(res, ensure_ascii=False)[:300]}")

        print("\n" + "=" * 84)
        print("FUTBIN via Playwright")
        print("=" * 84)
        started = time.perf_counter()
        try:
            page.goto(FUTBIN_URL, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(15_000)
            title = page.title()
            body = page.inner_text("body")[:200].replace("\n", " ")
            print(f"  after {time.perf_counter() - started:.1f}s  title={title!r}")
            print(f"  body: {body}")
            blocked = "moment" in title.lower() or "dakika" in title.lower()
            print(f"  VERDICT: {'STILL CHALLENGED' if blocked else 'passed'}")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED after {time.perf_counter() - started:.1f}s: {type(exc).__name__}: {exc}")

        browser.close()


if __name__ == "__main__":
    main()
