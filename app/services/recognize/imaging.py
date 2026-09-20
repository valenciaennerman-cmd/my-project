"""Image hashing and preparation.

Two different hashes, on purpose:
  * `content_hash` (SHA-256 of the bytes) answers "have I already processed this
    exact file?" -- that is the de-duplication the watcher needs.
  * `perceptual_hash` (dHash) answers "is this the same card as before?" and is
    what a remembered manual correction is keyed on, so a second screenshot of
    the same card at a different size still recalls the fix.

Full-screen screenshots are not cropped with heuristics; they are downscaled and
handed to the vision model, which locates the card itself. That avoids a brittle
card-detection step for a job the model already does well.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# Anthropic resizes anything larger; sending more pixels just costs tokens.
MAX_EDGE = 1568
# Card crops arrive tiny (the samples are ~150 px wide); a gentle upscale makes
# the rating and name legible without inventing detail.
MIN_EDGE = 640
DHASH_SIZE = 8


@dataclass(slots=True)
class PreparedImage:
    media_type: str
    base64_data: str
    width: int
    height: int
    was_resized: bool


def content_hash(path: Path) -> str:
    """SHA-256 of the file bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def perceptual_hash(path: Path) -> str:
    """Difference hash: robust to rescaling and mild compression."""
    with Image.open(path) as image:
        grey = image.convert("L").resize(
            (DHASH_SIZE + 1, DHASH_SIZE), Image.Resampling.LANCZOS
        )
        # Mode "L" is one byte per pixel, row-major -- no need for getdata(),
        # which Pillow 12 deprecates.
        pixels = grey.tobytes()

    bits = 0
    index = 0
    for row in range(DHASH_SIZE):
        offset = row * (DHASH_SIZE + 1)
        for col in range(DHASH_SIZE):
            left = pixels[offset + col]
            right = pixels[offset + col + 1]
            bits |= (1 if left > right else 0) << index
            index += 1
    return f"{bits:016x}"


def _flatten(image: Image.Image) -> Image.Image:
    """Composite transparency onto a dark background, matching the game UI."""
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        backdrop = Image.new("RGBA", image.size, (18, 18, 22, 255))
        image = Image.alpha_composite(backdrop, image)
    return image.convert("RGB")


def prepare_for_vision(path: Path) -> PreparedImage:
    """Normalise a screenshot into PNG bytes sized for the vision model."""
    with Image.open(path) as opened:
        image = _flatten(opened)
        original = image.size
        longest = max(image.size)

        if longest > MAX_EDGE:
            scale = MAX_EDGE / longest
            image = image.resize(
                (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        elif longest < MIN_EDGE:
            scale = MIN_EDGE / longest
            image = image.resize(
                (int(image.width * scale), int(image.height * scale)),
                Image.Resampling.LANCZOS,
            )

        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)

    return PreparedImage(
        media_type="image/png",
        base64_data=base64.standard_b64encode(buffer.getvalue()).decode("ascii"),
        width=image.width,
        height=image.height,
        was_resized=image.size != original,
    )


def looks_like_full_screen(path: Path) -> bool:
    """A wide, large image is probably a whole game screen, not a card crop."""
    try:
        with Image.open(path) as image:
            return image.width >= 900 and image.width > image.height
    except OSError as exc:
        logger.warning("%s olculemedi: %s", path.name, exc)
        return False
