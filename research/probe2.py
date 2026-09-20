from __future__ import annotations
import time
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1", "Connection": "keep-alive",
}
TARGETS = [
    ("FUTBIN_player", "https://www.futbin.com/27/player/21491/zidane"),
    ("FUTWIZ_home", "https://www.futwiz.com/en/"),
    ("FUTDB_home", "https://futdatabase.com/"),
    ("FUTGG_home", "https://www.fut.gg/"),
]
s = requests.Session(); s.headers.update(HEADERS)
for name, url in TARGETS:
    t0 = time.perf_counter()
    r = s.get(url, timeout=25)
    dt = time.perf_counter() - t0
    body = r.text
    open(f"research/body_{name}.html", "w", encoding="utf-8", errors="replace").write(body)
    title = body.split("<title>")[1].split("</title>")[0].strip()[:100] if "<title>" in body else "(none)"
    print(f"{name}: {r.status_code} {dt:.2f}s len={len(body)} enc={r.headers.get('content-encoding','-')}")
    print(f"   title: {title}")
    low = body.lower()
    hits = [m for m in ("cloudflare","just a moment","captcha","enable javascript","blocked",
                        "attention required","ray id","rate limit") if m in low]
    print(f"   markers: {hits}")
