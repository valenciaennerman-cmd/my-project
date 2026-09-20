"""Probe candidate price sources with realistic browser headers."""
from __future__ import annotations
import time, json, sys
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}

TARGETS = [
    ("FUTBIN player", "https://www.futbin.com/27/player/21491/zidane"),
    ("FUTWIZ home", "https://www.futwiz.com/en/"),
    ("FUTDB home", "https://futdatabase.com/"),
    ("FUTGG home", "https://www.fut.gg/"),
]

s = requests.Session()
s.headers.update(HEADERS)
for name, url in TARGETS:
    t0 = time.perf_counter()
    try:
        r = s.get(url, timeout=25, allow_redirects=True)
        dt = time.perf_counter() - t0
        body = r.text
        srv = r.headers.get("server", "-")
        cfray = r.headers.get("cf-ray", "-")
        print(f"\n=== {name} -> {r.status_code} in {dt:.2f}s  server={srv} cf-ray={cfray} len={len(body)}")
        low = body.lower()
        for marker in ("cloudflare", "just a moment", "cf-challenge", "captcha",
                       "enable javascript", "access denied", "rate limit", "too many requests",
                       "ddos-guard", "datadome", "perimeterx"):
            if marker in low:
                print(f"    marker: {marker!r}")
        print("    title:", (body.split("<title>")[1].split("</title>")[0].strip()[:90]
                             if "<title>" in body else "(none)"))
    except Exception as exc:
        print(f"\n=== {name} -> EXC {type(exc).__name__}: {exc}")
