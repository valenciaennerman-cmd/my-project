"""Can we get a PC price *history* series out of FUTWIZ?

The chart on a FUTWIZ player page has Console/PC toggles and Daily/Hourly
granularity. This finds out where that series comes from: an embedded blob, a
JSON endpoint the page calls, or only pixels.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright

URL = "https://www.futwiz.com/en/fc27/player/zinedine-zidane/111561"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

FIND_SERIES_JS = r"""() => {
  const out = { canvases: 0, svgPaths: 0, globals: [], inlineHits: [] };
  out.canvases = document.querySelectorAll('canvas').length;
  out.svgPaths = document.querySelectorAll('svg path').length;

  // Chart libraries usually leave the parsed series on window or on the canvas.
  for (const key of Object.keys(window)) {
    if (/chart|graph|price|series|highchart|apex|echart/i.test(key)) out.globals.push(key);
  }

  // Inline <script> blobs that look like a time series.
  for (const s of document.querySelectorAll('script:not([src])')) {
    const text = s.textContent || '';
    if (/price|chart|series/i.test(text) && /\[\s*[\[{]/.test(text)) {
      out.inlineHits.push(text.slice(0, 160).replace(/\s+/g, ' '));
    }
  }
  return out;
}"""


async def main() -> None:
    profile = Path("data/.probe-history")
    profile.mkdir(parents=True, exist_ok=True)
    calls: list[dict] = []

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            str(profile), headless=False, user_agent=UA,
            viewport={"width": 1440, "height": 950}, locale="en-US",
            args=["--disable-blink-features=AutomationControlled",
                  "--window-position=-32000,-32000"],
        )
        page = await ctx.new_page()

        async def on_response(resp):
            url = resp.url
            if resp.request.resource_type in ("image", "font", "stylesheet", "media"):
                return
            if not re.search(r"price|chart|graph|histor|sale", url, re.I):
                return
            entry = {"status": resp.status, "url": url[:150], "method": resp.request.method}
            try:
                body = await resp.text()
                entry["len"] = len(body)
                entry["head"] = body[:200].replace("\n", " ")
            except Exception as exc:  # noqa: BLE001
                entry["head"] = f"<unreadable: {type(exc).__name__}>"
            calls.append(entry)

        page.on("response", on_response)

        await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        for _ in range(30):
            await page.wait_for_timeout(700)
            if "moment" not in (await page.title()).lower():
                break
        print("title:", await page.title())
        await page.wait_for_timeout(6_000)

        # Try switching the chart to PC, which should trigger the series fetch.
        for label in ("PC", "Hourly"):
            try:
                btn = page.locator(f"button:has-text('{label}'), a:has-text('{label}')").first
                if await btn.count():
                    await btn.click(timeout=4_000)
                    print(f"clicked {label}")
                    await page.wait_for_timeout(4_000)
            except Exception as exc:  # noqa: BLE001
                print(f"{label} click failed: {type(exc).__name__}")

        found = await page.evaluate(FIND_SERIES_JS)
        print("\n-- page shape --")
        print(json.dumps(found, indent=2)[:900])

        print(f"\n-- price/chart-ish responses ({len(calls)}) --")
        for c in calls[:12]:
            print(f"  {c['status']} {c['method']} {c['url']}")
            print(f"      len={c.get('len')} head={c.get('head', '')[:130]}")

        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
