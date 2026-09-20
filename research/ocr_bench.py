"""Benchmark local OCR on the sample card screenshots.

Measures, per engine: wall time per image and whether the three hard facts the
matcher needs (name, rating, position) can be recovered from the raw OCR text.
Card type is deliberately not scored -- no OCR engine can report it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
import unicodedata
from pathlib import Path
from typing import Any

SAMPLES = Path("samples")
TRUTH = json.loads(Path("research/ground_truth.json").read_text(encoding="utf-8"))
POSITIONS = {
    "GK", "CB", "LB", "RB", "LWB", "RWB", "CDM", "CM", "CAM",
    "LM", "RM", "LW", "RW", "CF", "ST",
}


def fold(text: str) -> str:
    """Lowercase + strip accents so 'Martí' matches 'marti'."""
    text = text.replace("ı", "i").replace("İ", "i").replace("ç", "c").replace("ş", "s")
    text = text.replace("ğ", "g").replace("ö", "o").replace("ü", "u")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def score(tokens: list[str], truth: dict[str, Any]) -> dict[str, bool]:
    """Did the OCR output contain each fact we need?"""
    joined = fold(" ".join(tokens))
    squashed = re.sub(r"[^a-z0-9]", "", joined)

    surname = fold(truth["name"]).split()[-1]
    name_ok = surname in joined or re.sub(r"[^a-z]", "", surname) in squashed

    numbers = re.findall(r"\d{1,3}", joined)
    rating_ok = str(truth["rating"]) in numbers

    upper = {t.strip().upper() for t in tokens}
    pos_ok = truth["position"] in upper
    if not pos_ok:  # tolerate the position being glued to neighbouring text
        pos_ok = bool(re.search(rf"\b{truth['position']}\b", " ".join(tokens).upper()))

    return {"name": name_ok, "rating": rating_ok, "position": pos_ok}


def run_rapidocr(paths: list[Path]) -> dict[str, Any]:
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    engine(str(paths[0]))  # warm up; first call loads the ONNX models
    results = {}
    for path in paths:
        started = time.perf_counter()
        out, _ = engine(str(path))
        elapsed = time.perf_counter() - started
        tokens = [item[1] for item in out] if out else []
        results[path.name] = {"tokens": tokens, "seconds": elapsed}
    return results


def run_easyocr(paths: list[Path]) -> dict[str, Any]:
    import easyocr

    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    reader.readtext(str(paths[0]))  # warm up
    results = {}
    for path in paths:
        started = time.perf_counter()
        tokens = reader.readtext(str(path), detail=0)
        elapsed = time.perf_counter() - started
        results[path.name] = {"tokens": list(tokens), "seconds": elapsed}
    return results


ENGINES = {"rapidocr": run_rapidocr, "easyocr": run_easyocr}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", choices=sorted(ENGINES))
    args = parser.parse_args()

    paths = sorted(
        SAMPLES.glob("*.png"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0
    )
    load_started = time.perf_counter()
    results = ENGINES[args.engine](paths)
    total = time.perf_counter() - load_started

    print(f"\n{'=' * 92}\nENGINE: {args.engine}\n{'=' * 92}")
    print(f"{'file':<9}{'sec':>6}  {'name':^6}{'rate':^6}{'pos':^5}  raw tokens")
    print("-" * 92)

    tallies = {"name": 0, "rating": 0, "position": 0}
    times: list[float] = []
    for path in paths:
        res = results[path.name]
        truth = TRUTH[path.name]
        hits = score(res["tokens"], truth)
        for key, ok in hits.items():
            tallies[key] += ok
        times.append(res["seconds"])
        marks = "".join(("  OK  " if hits[k] else "  --  ") for k in ("name", "rating"))
        marks += " OK  " if hits["position"] else " --  "
        raw = " | ".join(res["tokens"])[:52]
        print(f"{path.name:<9}{res['seconds']:>6.2f}  {marks} {raw}")

    n = len(paths)
    print("-" * 92)
    print(
        f"name {tallies['name']}/{n}   rating {tallies['rating']}/{n}   "
        f"position {tallies['position']}/{n}"
    )
    all_three = sum(
        all(score(results[p.name]["tokens"], TRUTH[p.name]).values()) for p in paths
    )
    print(f"all three correct: {all_three}/{n}")
    print(
        f"per-image: median {statistics.median(times):.2f}s  "
        f"mean {statistics.mean(times):.2f}s  max {max(times):.2f}s"
    )
    print(f"total incl. model load: {total:.1f}s")

    out = Path(f"research/ocr_{args.engine}.json")
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"raw output -> {out}")


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    main()
