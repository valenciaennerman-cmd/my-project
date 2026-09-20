"""Dump the FUTWIZ price DOM for one card, so the provider's selectors are
written against what the page actually renders rather than a guess.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

DUMP_JS = r"""() => {
  const isPrice = (t) => /^\d{1,3}([,.]\d{3})+$/.test(t);
  const leaves = [...document.querySelectorAll('*')].filter(e => !e.children.length);

  const prices = leaves
    .filter(e => isPrice(e.textContent.trim()))
    .slice(0, 8)
    .map(e => ({
      text: e.textContent.trim(),
      cls: (e.className || '').toString().slice(0, 70),
      parentCls: (e.parentElement ? e.parentElement.className : '').toString().slice(0, 70)
    }));

  const labels = leaves
    .filter(e => ['PC', 'Console', 'CONSOLE'].includes(e.textContent.trim()))
    .map(e => ({ text: e.textContent.trim(), cls: (e.className || '').toString().slice(0, 50) }));

  // Smallest containers that hold a price, with their platform icons.
  const boxes = [...document.querySelectorAll('div')]
    .filter(d => [...d.querySelectorAll('*')].some(e => !e.children.length && isPrice(e.textContent.trim())))
    .filter(d => (d.innerText || '').length < 220);

  const containers = boxes.slice(0, 8).map(d => ({
    cls: (d.className || '').toString().slice(0, 90),
    icons: [...d.querySelectorAll('svg[data-icon]')].map(s => s.getAttribute('data-icon')),
    text: (d.innerText || '').replace(/\s*\n\s*/g, ' | ').slice(0, 110)
  }));

  return { prices, labels, containers, title: document.title };
}"""


async def main(url: str) -> None:
    profile = Path("data/.probe-search")
    profile.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            str(profile),
            headless=False,
            user_agent=UA,
            viewport={"width": 1366, "height": 900},
            locale="en-US",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--window-position=-32000,-32000",
            ],
        )
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        for _ in range(30):
            await page.wait_for_timeout(700)
            if "moment" not in (await page.title()).lower():
                break
        await page.wait_for_timeout(5_000)

        data = await page.evaluate(DUMP_JS)
        print("title:", data["title"])
        print("\n-- price leaves --")
        for item in data["prices"]:
            print("   ", json.dumps(item, ensure_ascii=False))
        print("\n-- platform labels --", data["labels"])
        print("\n-- containers holding a price --")
        for item in data["containers"]:
            print("   ", json.dumps(item, ensure_ascii=False))
        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
