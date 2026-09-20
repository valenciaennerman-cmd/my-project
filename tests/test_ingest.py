"""Screenshot intake: waiting for a complete file, and not reading one twice."""
from __future__ import annotations

import asyncio
from pathlib import Path

from PIL import Image

from app.services.ingest.clipboard import MIN_EDGE, image_fingerprint
from app.services.ingest.folder import (
    FileStat,
    FolderWatcher,
    is_stable,
    wait_until_written,
)
from app.services.recognize.imaging import content_hash, perceptual_hash


def write_png(path: Path, size=(140, 170), colour=(200, 40, 40)) -> Path:
    Image.new("RGB", size, colour).save(path, format="PNG")
    return path


class TestStabilityCheck:
    def test_identical_samples_are_stable(self):
        samples = [FileStat(1000, 5)] * 3
        assert is_stable(samples)

    def test_a_growing_file_is_not_stable(self):
        samples = [FileStat(100, 1), FileStat(500, 2), FileStat(900, 3)]
        assert not is_stable(samples)

    def test_only_the_trailing_window_matters(self):
        samples = [FileStat(1, 1), FileStat(2, 2), FileStat(9, 9), FileStat(9, 9), FileStat(9, 9)]
        assert is_stable(samples)

    def test_zero_byte_file_is_never_stable(self):
        assert not is_stable([FileStat(0, 1)] * 3)

    def test_missing_file_is_never_stable(self):
        assert not is_stable([None] * 3)

    def test_too_few_samples(self):
        assert not is_stable([FileStat(10, 1), FileStat(10, 1)])


class TestWaitUntilWritten:
    async def test_returns_true_for_a_finished_file(self, tmp_path):
        path = write_png(tmp_path / "shot.png")
        assert await wait_until_written(path, interval=0.01, timeout=2.0)

    async def test_waits_while_the_file_is_still_growing(self, tmp_path):
        """The watcher must not hash a half-written screenshot."""
        path = tmp_path / "slow.png"
        path.write_bytes(b"\x89PNG" + b"0" * 100)
        finished = False

        async def grow():
            nonlocal finished
            for _ in range(4):
                await asyncio.sleep(0.03)
                with path.open("ab") as handle:
                    handle.write(b"0" * 500)
            finished = True

        grower = asyncio.create_task(grow())
        ok = await wait_until_written(path, interval=0.02, timeout=5.0)
        await grower
        assert ok
        assert finished, "returned before the writer was done"

    async def test_gives_up_on_a_file_that_never_settles(self, tmp_path):
        path = tmp_path / "never.png"
        path.write_bytes(b"x")

        async def sleeper(_seconds: float) -> None:
            # Grow the file on every poll so it can never stabilise.
            with path.open("ab") as handle:
                handle.write(b"y")

        assert not await wait_until_written(
            path, interval=0.001, timeout=0.05, sleep=sleeper
        )

    async def test_missing_file_times_out_rather_than_raising(self, tmp_path):
        assert not await wait_until_written(
            tmp_path / "ghost.png", interval=0.01, timeout=0.1
        )


class TestFolderWatcher:
    async def test_files_present_at_start_are_not_processed(self, tmp_path):
        """Opening the app must not scan a folder full of old screenshots."""
        write_png(tmp_path / "old1.png")
        write_png(tmp_path / "old2.png")
        seen: list[Path] = []

        watcher = _watcher(tmp_path, lambda p: _record(seen, p))
        watcher.start()
        await asyncio.sleep(0.15)
        await watcher.stop()

        assert seen == []

    async def test_a_new_file_is_processed_once(self, tmp_path):
        seen: list[Path] = []
        watcher = _watcher(tmp_path, lambda p: _record(seen, p))
        watcher.start()
        await asyncio.sleep(0.05)

        write_png(tmp_path / "new.png")
        await asyncio.sleep(0.5)
        await watcher.stop()

        assert [p.name for p in seen] == ["new.png"]

    async def test_unwatched_extensions_are_ignored(self, tmp_path):
        seen: list[Path] = []
        watcher = _watcher(tmp_path, lambda p: _record(seen, p))
        watcher.start()
        await asyncio.sleep(0.05)
        (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
        await asyncio.sleep(0.2)
        await watcher.stop()
        assert seen == []

    async def test_paused_watcher_does_not_process(self, tmp_path):
        seen: list[Path] = []
        watcher = _watcher(tmp_path, lambda p: _record(seen, p))
        watcher.start()
        watcher.pause()
        await asyncio.sleep(0.05)
        write_png(tmp_path / "while-paused.png")
        await asyncio.sleep(0.2)
        assert seen == []

        # Resuming must not replay what arrived while paused.
        watcher.resume()
        await asyncio.sleep(0.2)
        await watcher.stop()
        assert seen == []

    async def test_a_failing_callback_does_not_stop_the_watcher(self, tmp_path):
        calls: list[str] = []

        async def explode(path: Path) -> None:
            calls.append(path.name)
            raise RuntimeError("boom")

        watcher = _watcher(tmp_path, explode)
        watcher.start()
        await asyncio.sleep(0.05)
        write_png(tmp_path / "a.png")
        await asyncio.sleep(0.4)
        write_png(tmp_path / "b.png")
        await asyncio.sleep(0.4)
        await watcher.stop()

        assert sorted(calls) == ["a.png", "b.png"]
        assert watcher.last_error and "boom" in watcher.last_error

    async def test_missing_directory_is_reported_not_raised(self, tmp_path):
        watcher = _watcher(tmp_path / "nope", lambda p: _record([], p))
        watcher.start()
        await asyncio.sleep(0.1)
        await watcher.stop()
        assert watcher.status()["directory_exists"] is False
        assert "nope" in (watcher.last_error or "")


class TestHashing:
    def test_identical_bytes_share_a_content_hash(self, tmp_path):
        a = write_png(tmp_path / "a.png")
        b = tmp_path / "b.png"
        b.write_bytes(a.read_bytes())
        assert content_hash(a) == content_hash(b)

    def test_different_images_differ(self, tmp_path):
        a = write_png(tmp_path / "a.png", colour=(10, 10, 10))
        b = write_png(tmp_path / "b.png", colour=(250, 250, 250))
        assert content_hash(a) != content_hash(b)

    def test_perceptual_hash_survives_rescaling(self, tmp_path):
        """Samples 9 and 10 are the same card at two sizes."""
        source = tmp_path / "big.png"
        Image.new("RGB", (240, 290)).save(source)
        image = Image.open(source)
        for x in range(240):  # a gradient, so the hash has something to key on
            for y in range(0, 290, 29):
                image.putpixel((x, y), (x % 256, (x * 2) % 256, 60))
        image.save(source)

        small = tmp_path / "small.png"
        image.resize((120, 145), Image.Resampling.LANCZOS).save(small)

        assert perceptual_hash(source) == perceptual_hash(small)
        # ...while the byte hashes do not match.
        assert content_hash(source) != content_hash(small)

    def test_clipboard_fingerprint_is_stable_and_distinguishing(self):
        red = Image.new("RGB", (100, 120), (200, 20, 20))
        red_again = Image.new("RGB", (100, 120), (200, 20, 20))
        blue = Image.new("RGB", (100, 120), (20, 20, 200))
        assert image_fingerprint(red) == image_fingerprint(red_again)
        assert image_fingerprint(red) != image_fingerprint(blue)

    def test_min_edge_guard_is_sane(self):
        assert 0 < MIN_EDGE < 140


async def _record(bucket: list[Path], path: Path) -> None:
    bucket.append(path)


def _watcher(directory, callback) -> FolderWatcher:
    """A watcher tuned for tests: short polls, short stability window."""
    return FolderWatcher(
        directory,
        (".png",),
        callback,
        poll_interval=0.02,
        stable_checks=2,
        stable_interval=0.01,
        stable_timeout=1.0,
    )
