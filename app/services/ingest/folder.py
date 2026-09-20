"""Watch a folder for newly-arrived screenshots.

Three things this has to get right:
  * only files that appear *after* the app starts are processed -- an existing
    folder full of old screenshots must not be scanned on launch;
  * a file is not read until it is fully written, or we hash and OCR a
    half-flushed PNG;
  * the same image is never processed twice, keyed on its content hash.

Polling rather than filesystem events: on Windows a create event fires long
before the writer is done, so we would have to poll for stability anyway.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Iterable

logger = logging.getLogger(__name__)

# A file counts as finished once its size and mtime stop changing.
STABLE_CHECKS = 3
STABLE_INTERVAL = 0.25
STABLE_TIMEOUT = 20.0


@dataclass(frozen=True, slots=True)
class FileStat:
    size: int
    mtime_ns: int


def _stat(path: Path) -> FileStat | None:
    try:
        info = path.stat()
    except OSError:
        return None
    return FileStat(size=info.st_size, mtime_ns=info.st_mtime_ns)


def is_stable(samples: Iterable[FileStat | None], required: int = STABLE_CHECKS) -> bool:
    """True when the last `required` samples are identical and non-empty."""
    window = list(samples)[-required:]
    if len(window) < required:
        return False
    first = window[0]
    if first is None or first.size <= 0:
        return False
    return all(sample == first for sample in window)


async def wait_until_written(
    path: Path,
    required: int = STABLE_CHECKS,
    interval: float = STABLE_INTERVAL,
    timeout: float = STABLE_TIMEOUT,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> bool:
    """Block until `path` stops changing size. False if it never settles."""
    samples: list[FileStat | None] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        samples.append(_stat(path))
        if is_stable(samples, required):
            return True
        await sleep(interval)
    logger.warning("%s zaman asimina kadar yazilmayi bitirmedi", path.name)
    return False


class FolderWatcher:
    """Polls a folder and hands each newly-finished file to a callback."""

    def __init__(
        self,
        directory: Path,
        extensions: tuple[str, ...],
        on_new_file: Callable[[Path], Awaitable[None]],
        poll_interval: float = 1.0,
        stable_checks: int = STABLE_CHECKS,
        stable_interval: float = STABLE_INTERVAL,
        stable_timeout: float = STABLE_TIMEOUT,
    ) -> None:
        self.directory = directory
        self.extensions = tuple(e.lower() for e in extensions)
        self._on_new_file = on_new_file
        self._poll_interval = poll_interval
        self._stable_checks = stable_checks
        self._stable_interval = stable_interval
        self._stable_timeout = stable_timeout

        self._enabled = False
        self._task: asyncio.Task | None = None
        self._seen: set[str] = set()
        self._started_at = 0.0
        self.last_error: str | None = None

    # -- state -------------------------------------------------------------
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
            "directory": str(self.directory),
            "directory_exists": self.directory.is_dir(),
            "extensions": list(self.extensions),
            "seen_count": len(self._seen),
            "last_error": self.last_error,
        }

    # -- control -----------------------------------------------------------
    def start(self) -> None:
        """Begin watching. Files already present are recorded, not processed."""
        if self.running:
            self._enabled = True
            return
        self._started_at = time.time()
        self._seen = set(self._current_files())
        self._enabled = True
        self.last_error = None
        self._task = asyncio.create_task(self._loop(), name="folder-watcher")
        logger.info(
            "izleme basladi: %s (%d mevcut dosya atlandi)",
            self.directory, len(self._seen),
        )

    def pause(self) -> None:
        self._enabled = False
        logger.info("izleme duraklatildi")

    def resume(self) -> None:
        """Resume without re-processing anything that arrived while paused."""
        self._seen |= set(self._current_files())
        self._enabled = True
        if not self.running:
            self.start()
        logger.info("izleme devam ediyor")

    async def stop(self) -> None:
        self._enabled = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # -- internals ---------------------------------------------------------
    def _current_files(self) -> list[str]:
        if not self.directory.is_dir():
            return []
        return [
            str(p)
            for p in self.directory.iterdir()
            if p.is_file() and p.suffix.lower() in self.extensions
        ]

    def _is_new(self, path: Path) -> bool:
        if str(path) in self._seen:
            return False
        try:
            # Guard against a file that merely *moved* into the folder with an
            # old timestamp -- we only want genuinely fresh screenshots.
            return path.stat().st_mtime >= self._started_at - 2.0
        except OSError:
            return False

    async def _loop(self) -> None:
        while True:
            try:
                if self._enabled:
                    await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - loop must survive one bad file
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("izleme dongusunde hata")
            await asyncio.sleep(self._poll_interval)

    def _missing_directory_message(self) -> str:
        return f"Izlenen klasor yok: {self.directory}"

    async def _tick(self) -> None:
        if not self.directory.is_dir():
            message = self._missing_directory_message()
            if self.last_error != message:
                logger.warning(message)
                self.last_error = message
            return

        # Clear only the "folder is missing" complaint once it comes back.
        # A file-processing error stays visible until the next file succeeds,
        # otherwise the next poll would wipe it before the UI ever showed it.
        if self.last_error == self._missing_directory_message():
            self.last_error = None

        for raw in sorted(self._current_files()):
            path = Path(raw)
            if not self._is_new(path):
                self._seen.add(raw)
                continue

            self._seen.add(raw)
            if not await wait_until_written(
                path,
                required=self._stable_checks,
                interval=self._stable_interval,
                timeout=self._stable_timeout,
            ):
                continue

            logger.info("yeni ekran goruntusu: %s", path.name)
            try:
                await self._on_new_file(path)
            except Exception as exc:  # noqa: BLE001 - one failure must not stop watching
                self.last_error = f"{path.name}: {type(exc).__name__}: {exc}"
                logger.exception("%s islenemedi", path.name)
            else:
                self.last_error = None
