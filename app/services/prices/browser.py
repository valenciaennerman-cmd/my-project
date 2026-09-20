"""Shared headless browser for sources that only render prices client-side.

Deliberate constraints, because these sites are someone else's infrastructure:
  * one navigation at a time, never concurrent;
  * a minimum gap between navigations;
  * a persistent profile so a cleared challenge cookie is reused instead of
    forcing a fresh check on every visit;
  * no anti-detection patching. If a site challenges us, we wait the configured
    budget and then give up with a clear reason.

Measured behaviour (research/FINDINGS.md): FUTWIZ clears in ~1.5 s when it is
happy and simply will not clear during a burst, so pacing is the whole game.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

CHALLENGE_MARKERS = ("just a moment", "bir dakika", "security verification",
                     "attention required", "checking your browser")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class BrowserUnavailable(RuntimeError):
    """The browser could not be started -- usually Playwright is not installed."""


class ChallengeNotCleared(RuntimeError):
    """A bot check was shown and did not clear within the budget."""


class BrowserPool:
    """A single, lazily started, politely paced browser context."""

    def __init__(
        self,
        profile_dir: Path,
        min_interval: float = 6.0,
        challenge_timeout: float = 25.0,
        headless: bool = False,
        offscreen: bool = True,
    ) -> None:
        self._profile_dir = profile_dir
        self._min_interval = min_interval
        self._challenge_timeout = challenge_timeout
        self._headless = headless
        self._offscreen = offscreen

        self._playwright = None
        self._context: BrowserContext | None = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()
        self._last_navigation = 0.0

    async def _ensure_context(self) -> BrowserContext:
        if self._context is not None:
            return self._context
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        args = ["--disable-blink-features=AutomationControlled"]
        if not self._headless and self._offscreen:
            # A real window clears the bot checks; parking it off-screen keeps
            # it out of the way while the game is in focus.
            args += ["--window-position=-32000,-32000", "--window-size=1366,900"]
        try:
            self._playwright = await async_playwright().start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                str(self._profile_dir),
                headless=self._headless,
                user_agent=USER_AGENT,
                viewport={"width": 1366, "height": 900},
                locale="en-US",
                args=args,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced with guidance
            raise BrowserUnavailable(
                "Tarayici baslatilamadi. 'python -m playwright install chromium' "
                f"calistirdin mi? ({type(exc).__name__}: {exc})"
            ) from exc
        logger.info(
            "tarayici baslatildi (headless=%s, profil: %s)",
            self._headless, self._profile_dir,
        )
        return self._context

    async def _respect_pacing(self) -> None:
        elapsed = time.monotonic() - self._last_navigation
        if elapsed < self._min_interval:
            wait = self._min_interval - elapsed
            logger.debug("kaynagi yormamak icin %.1f sn bekleniyor", wait)
            await asyncio.sleep(wait)

    async def _settle(self, page: Page) -> None:
        """Wait out a bot check, if one is showing."""
        deadline = time.monotonic() + self._challenge_timeout
        while time.monotonic() < deadline:
            title = (await page.title()).lower()
            if not any(marker in title for marker in CHALLENGE_MARKERS):
                return
            await page.wait_for_timeout(700)
        raise ChallengeNotCleared(
            f"Bot dogrulamasi {self._challenge_timeout:.0f} sn icinde gecilmedi."
        )

    async def open(self, url: str, settle: bool = True) -> Page:
        """Navigate to `url` and return the page. Caller must close it.

        Serialised: only one page load happens at a time across the whole app.
        """
        await self._lock.acquire()
        page: Page | None = None
        try:
            context = await self._ensure_context()
            await self._respect_pacing()
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            self._last_navigation = time.monotonic()
            if settle:
                await self._settle(page)
            return page
        except Exception:
            if page is not None:
                await page.close()
            self._lock.release()
            raise

    async def release(self, page: Page) -> None:
        try:
            await page.close()
        finally:
            if self._lock.locked():
                self._lock.release()

    async def aclose(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        logger.info("tarayici kapatildi")
