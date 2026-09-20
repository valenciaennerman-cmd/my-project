"""How often does FUTWIZ actually publish a PC price?

The whole tool leans on FUTWIZ for PC numbers, so it matters whether that data
is dense or sparse. Samples a handful of cards across rating bands.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

CARDS = [
    ("Mbappe 91 Rare", "https://www.futwiz.com/en/fc27/player/kylian-mbappe/27"),
    ("Iniesta 92 Icon", "https://www.futwiz.com/en/fc27/player/andres-iniesta/111581"),
    ("Zidane 94 Icon", "https://www.futwiz.com/en/fc27/player/zinedine-zidane/111561"),
    ("Zidane 94 Icon (2)", "https://www.futwiz.com/en/fc27/player/zinedine-zidane/111560"),
    ("Pele 95 Icon", "https://www.futwiz.com/en/fc27/player/pele/111559"),
    ("Ethan Mbappe 74", "https://www.futwiz.com/en/fc27/player/ethan-mbappe/2750"),
]

READ_JS = r"""() => {
  const isPrice = (t) => /^\d{1,3}([,.]\d{3})+$/.test(t);
  const boxes = [...document.querySelectorAll('div.flex.flex-row.items-center')];
  const out = [];
  for (const box of boxes) {
    const leaves = [...box.querySelectorAll('*')].filter(e => !e.children.length);
    const priceEl = leaves.find(e => isPrice(e.textContent.trim()));
    const icons = [...box.querySelectorAll('svg[data-icon]')].map(e => e.getAttribute('data-icon'));
    const hasPcLabel = leaves.some(e => e.textContent.trim() === 'PC');
    const unavailable = (box.innerText || '').toLowerCase().includes('unavailable');
    if (!priceEl && !unavailable) continue;
    out.push({
      price: priceEl ? priceEl.textContent.trim() : null,
      icons, hasPcLabel, unavailable,
      text: (box.innerText || '').replace(/\s*\n\s*/g, ' | ').slice(0, 90)
    });
  }
  return out;
}"""


async def settle(page) -> bool:
    for _ in range(30):
        await page.wait_for_timeout(700)
        if "moment" not in (await page.title()).lower():
            return True
    return False


async def main() -> None:
    profile = Path("data/.probe-search")
    profile.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            str(profile), headless=False, user_agent=UA,
            viewport={"width": 1366, "height": 900}, locale="en-US",
            args=["--disable-blink-features=AutomationControlled",
                  "--window-position=-32000,-32000"],
        )
        page = await ctx.new_page()
        with_pc = 0
        for label, url in CARDS:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            if not await settle(page):
                print(f"{label:<22} CHALLENGED")
                continue
            await page.wait_for_timeout(4_000)
            blocks = await page.evaluate(READ_JS)
            pc = next((b for b in blocks if b["hasPcLabel"] or "computer" in (b["icons"] or [])), None)
            console = next((b for b in blocks if b is not pc and b["price"]), None)
            has_pc = bool(pc and pc["price"])
            with_pc += has_pc
            print(
                f"{label:<22} PC={pc['price'] if has_pc else ('unavailable' if pc else 'no block'):<12}"
                f" console={console['price'] if console else '-'}"
            )
            await page.wait_for_timeout(6_000)
        print(f"\nPC price available on {with_pc}/{len(CARDS)} sampled cards")
        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
