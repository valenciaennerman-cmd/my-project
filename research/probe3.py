from __future__ import annotations
import re, time, json
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
     "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "gzip, deflate"}
s = requests.Session(); s.headers.update(H)

# 1) FUT.GG homepage: what link shapes exist?
r = s.get("https://www.fut.gg/", timeout=25)
html = r.text
hrefs = sorted(set(re.findall(r'href="(/[^"#?]*)"', html)))
print("FUT.GG href shapes (sample):")
for h in hrefs[:60]:
    print("   ", h)
print("total hrefs:", len(hrefs))

# 2) Look for player-ish paths
players = [h for h in hrefs if "player" in h]
print("\nplayer-ish:", players[:20])

# 3) framework hints
for pat in ("__NEXT_DATA__", "_next/", "htmx", "turbo", "vite", "astro", "/static/"):
    print(f"   hint {pat}: {html.count(pat)}")
