"""Read card screenshots straight off the Windows clipboard.

Win+Shift+S, drag a box around the card, done -- no file to save. The clipboard
keeps holding the same image after we read it, so each grab is hashed and a
repeat of the last image is ignored.

Grabbed images are written into an inbox folder so the rest of the pipeline
(hashing, the scan record, the UI's thumbnail endpoint) can treat them exactly
like a screenshot that arrived on disk.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Awaitable, Callable

from PIL import Image, ImageGrab

logger = logging.getLogger(__name__)

# Anything smaller than this is not a card screenshot.
MIN_EDGE = 60


def grab() -> Image.Image | None:
    """Return the clipboard image, or None when it holds something else.

    Pillow raises on some non-image clipboard payloads and on X11 without a
    display; both mean "no image", not a bug worth crashing the loop over.
    """
    try:
        data = ImageGrab.grabclipboard()
    except (OSError, NotImplementedError) as exc:
        logger.debug("pano okunamadi: %s", exc)
        return None

    if isinstance(data, Image.Image):
        return data
    if isinstance(data, list) and data:
        # The clipboard holds copied *files* rather than pixels.
        first = Path(str(data[0]))
        if first.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp") and first.is_file():
            try:
                with Image.open(first) as opened:
                    return opened.copy()
            except OSError as exc:
                logger.warning("panodaki dosya acilamadi (%s): %s", first.name, exc)
    return None


def image_fingerprint(image: Image.Image) -> str:
    """Stable hash of the pixels, used to ignore an unchanged clipboard."""
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=False, compress_level=1)
    return hashlib.sha256(buffer.getvalue()).hexdigest()


class ClipboardWatcher:
    """Polls the clipboard and saves any new image into `inbox`."""

    def __init__(
        self,
        inbox: Path,
        on_new_file: Callable[[Path], Awaitable[None]],
        poll_interval: float = 1.2,
        enabled: bool = False,
    ) -> None:
        self.inbox = inbox
        self._on_new_file = on_new_file
        self._poll_interval = poll_interval
        self._enabled = enabled
        self._task: asyncio.Task | None = None
        self._last_fingerprint: str | None = None
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "running": self.running,
            "inbox": str(self.inbox),
            "last_error": self.last_error,
        }

    def start(self) -> None:
        if self.running:
            return
        self.inbox.mkdir(parents=True, exist_ok=True)
        # Whatever is already on the clipboard predates us; do not process it.
        current = grab()
        self._last_fingerprint = image_fingerprint(current) if current else None
        self._task = asyncio.create_task(self._loop(), name="clipboard-watcher")
        logger.info("pano izleme dongusu basladi (aktif=%s)", self._enabled)

    def pause(self) -> None:
        self._enabled = False

    def resume(self) -> None:
        # Skip whatever is sitting there right now, same reasoning as start().
        current = grab()
        self._last_fingerprint = image_fingerprint(current) if current else None
        self._enabled = True
        if not self.running:
            self.start()

    async def stop(self) -> None:
        self._enabled = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                if self._enabled:
                    await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - loop must outlive one bad grab
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("pano dongusunde hata")
            await asyncio.sleep(self._poll_interval)

    async def _tick(self) -> None:
        image = await asyncio.to_thread(grab)
        if image is None:
            return
        if min(image.size) < MIN_EDGE:
            return

        fingerprint = image_fingerprint(image)
        if fingerprint == self._last_fingerprint:
            return
        self._last_fingerprint = fingerprint

        path = self.inbox / f"clip-{datetime.now():%Y%m%d-%H%M%S}-{fingerprint[:8]}.png"
        await asyncio.to_thread(_save, image, path)
        self.last_error = None
        logger.info("panodan yeni gorsel: %s (%dx%d)", path.name, *image.size)

        try:
            await self._on_new_file(path)
        except Exception as exc:  # noqa: BLE001 - one bad image must not stop polling
            self.last_error = f"{path.name}: {type(exc).__name__}: {exc}"
            logger.exception("%s islenemedi", path.name)


def _save(image: Image.Image, path: Path) -> None:
    image.convert("RGB").save(path, format="PNG", optimize=True)
