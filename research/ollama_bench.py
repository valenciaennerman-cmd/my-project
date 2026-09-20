"""Benchmark a local Ollama vision model on the sample card screenshots.

Same 16 images and same ground truth as the OCR benchmark, so the numbers are
directly comparable with research/FINDINGS.md section 3.

Usage:  python research/ollama_bench.py qwen3.5:0.8b
"""
from __future__ import annotations

import argparse
import base64
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SAMPLES = Path("samples")
TRUTH = json.loads(Path("research/ground_truth.json").read_text(encoding="utf-8"))
ENDPOINT = "http://localhost:11434/api/chat"

SYSTEM = """You read EA Sports FC 27 Ultimate Team player cards from screenshots.

Card layout: the large number in the top-left is the overall rating, the short
code directly beneath it is the primary position, and the player's name runs
across the card near the bottom above the six stat abbreviations (PAC/SHO/PAS/
DRI/DEF/PHY, or DIV/HAN/KIC/REF/SPD/POS for goalkeepers).

Rules:
- Read the rating from the top-left corner only. Never report a stat value.
- Copy the name exactly as printed, keeping accents.
- '++' or '+' next to the position are chemistry markers, not the position.
- Note whether the card art looks holographic (iridescent pink/purple shimmer).
- If no player card is visible, set is_card to false."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_card": {"type": "boolean"},
        "name": {"type": "string"},
        "rating": {"type": "integer"},
        "position": {"type": "string"},
        "card_type": {
            "type": "string",
            "enum": ["bronze", "silver", "gold", "gold_rare", "totw", "icon",
                     "hero", "hall_of_fut", "special", "unknown"],
        },
        "card_style_description": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["is_card", "name", "rating", "position", "card_type",
                 "card_style_description", "confidence"],
}


def read_card(model: str, image_b64: str, think: bool, timeout: float,
              num_predict: int = 700) -> tuple[dict | None, float, str]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Read this card.", "images": [image_b64]},
        ],
        "stream": False,
        "think": think,
        "format": SCHEMA,
        "options": {"temperature": 0, "num_predict": num_predict},
    }
    request = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return None, time.perf_counter() - started, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - reported per image, never swallowed
        return None, time.perf_counter() - started, f"{type(exc).__name__}"

    elapsed = time.perf_counter() - started
    content = (body.get("message") or {}).get("content", "")
    try:
        return json.loads(content), elapsed, ""
    except json.JSONDecodeError:
        return None, elapsed, f"bad JSON: {content[:60]!r}"


def normalise(value: str | None) -> str:
    import re
    import unicodedata

    if not value:
        return ""
    swaps = {"ı": "i", "İ": "i", "ş": "s", "ğ": "g", "ç": "c", "ö": "o", "ü": "u"}
    for src, dst in swaps.items():
        value = value.replace(src, dst)
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", stripped.lower())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("--think", action="store_true", help="enable the model's thinking mode")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--num-predict", type=int, default=700,
                        help="output token budget; thinking needs room for both "
                             "the reasoning and the JSON")
    args = parser.parse_args()

    paths = sorted(SAMPLES.glob("*.png"), key=lambda p: int(p.stem))

    # Warm the model so the first image is not charged for the load.
    first = base64.standard_b64encode(paths[0].read_bytes()).decode()
    print(f"warming {args.model} (think={args.think}, num_predict={args.num_predict})...", flush=True)
    _, warm, warm_err = read_card(args.model, first, args.think, args.timeout, args.num_predict)
    print(f"warm-up: {warm:.1f}s {warm_err}\n")

    print(f"{'file':<9}{'sec':>7}  {'name':^6}{'rate':^6}{'pos':^5}{'type':^6}  read")
    print("-" * 92)

    tallies = {"name": 0, "rating": 0, "position": 0, "card_type": 0}
    times: list[float] = []
    failures: list[str] = []

    for path in paths:
        image = base64.standard_b64encode(path.read_bytes()).decode()
        data, elapsed, error = read_card(args.model, image, args.think, args.timeout, args.num_predict)
        times.append(elapsed)

        if data is None:
            failures.append(f"{path.name}: {error}")
            print(f"{path.name:<9}{elapsed:>7.1f}  {'FAILED':^23}  {error}")
            continue

        truth = TRUTH[path.name]
        got_name = normalise(data.get("name"))
        want_name = normalise(truth["name"])
        name_ok = bool(got_name) and (
            want_name in got_name or got_name in want_name
            or normalise(truth["name"].split()[-1]) in got_name
        )
        rating_ok = data.get("rating") == truth["rating"]
        pos_ok = str(data.get("position", "")).strip().upper() == truth["position"]
        type_ok = str(data.get("card_type", "")).strip().lower() == truth["card_type"]

        for key, ok in (("name", name_ok), ("rating", rating_ok),
                        ("position", pos_ok), ("card_type", type_ok)):
            tallies[key] += ok

        marks = "".join(" OK  " if ok else " --  " for ok in (name_ok, rating_ok, pos_ok, type_ok))
        got = f"{data.get('name')} {data.get('rating')} {data.get('position')} {data.get('card_type')}"
        print(f"{path.name:<9}{elapsed:>7.1f}  {marks} {got[:44]}")

    total = len(paths)
    print("-" * 92)
    print(
        f"name {tallies['name']}/{total}   rating {tallies['rating']}/{total}   "
        f"position {tallies['position']}/{total}   card_type {tallies['card_type']}/{total}"
    )
    if times:
        print(
            f"per image: median {statistics.median(times):.1f}s  "
            f"mean {statistics.mean(times):.1f}s  max {max(times):.1f}s"
        )
    if failures:
        print(f"failed: {len(failures)} -> {failures[:4]}")


if __name__ == "__main__":
    main()
