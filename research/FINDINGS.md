# Pre-build research findings — 2026-09-20

All numbers below were measured on this machine, not assumed. Scripts live in
`research/`; raw HTML/JSON captures are alongside them.

## 1. Price sources

| Source | plain `requests` | headless Chromium | PC price | measured speed |
|---|---|---|---|---|
| FUTBIN | 403 Cloudflare challenge (even `/robots.txt`) | **still challenged after 15.5 s** | n/a | n/a |
| FUT.GG | **200**, metadata fully server-rendered | price hydrates in **1.22 s** | **no — `ps5` only** | 0.3–0.5 s/page |
| FUTWIZ | 403 Cloudflare challenge | passes *intermittently* | **yes — Console + PC** | 1.4–1.7 s pass / 18 s+ when challenged |
| FUTDatabase | 401 without key | n/a | **yes (`pc` + `playstation`)** | n/a |

### FUTBIN — rejected
`www.futbin.com` returns a Cloudflare "Just a moment…" interstitial to every
non-browser client, including `robots.txt` itself. Real headless Chromium sat on
the challenge for 15.5 s and never cleared it. Only `cdn.futbin.com` (card
images, keyed by EA player id) answers. Getting through would mean actively
defeating the bot check — not done, not recommended.

### FUT.GG — best metadata source, wrong market for prices
* `/players/{baseId}-{slug}/27-{eaId}/` is server-rendered and robots-allowed.
* `sitemap-player-detail-27.xml` — 21 pages × 1000 URLs ≈ **21 000 FC 27 cards**,
  ~315 KB total. Legitimate catalog index.
* Prices are **not** in the HTML (`currentDbPrice: null`). They load from
  `GET /api/fut/player-prices/27/{eaId}/?verify=<sig>`, where the signature comes
  from `POST /api/fut/price-access/sign/`. Unsigned → 403. `/api/*` is also
  `Disallow`ed in robots.txt. Reimplementing that signing flow is circumvention;
  not done.
* Payload (observed via the page's own request) is `platform: "ps5"` with no PC
  figure anywhere.

### FUTWIZ — the only free PC price
* `/en/fc27/player/{slug}/{futwizId}` is **not** disallowed in robots.txt
  (`Disallow` covers `/*/players?*`, `/app/*`, settings, comments, login).
  Content-Signal is `search=yes, ai-train=no`.
* Shows Console and PC prices side by side. Iniesta 92 Icon:
  Console **1 370 000** vs PC **2 850 000**.
* Cloudflare passes for occasional loads but clamps down on bursts: request 1
  cleared in 1.4 s, requests 2 and 3 (≈4 s apart) never cleared within 17.5 s.
  Usable at one-card-at-a-time pace with caching and backoff; not for bulk.

### FUTDatabase — legitimate but paid
API spec version is **27**, so FC 27 data exists. `PricesResponse` carries both
`pc` and `playstation`. But `/players/{id}/price`, `/players/prices` and
`/players/search` are all marked *premium only*, and premium is **€79/month**
(20 000 req/day). Free tier also nulls some stats. `PlayerModel` exposes
`futBinId` and `futWizId`, which would be a clean cross-site bridge — value
unknown on the free tier without a key.

### Market structure (why PC matters)
In FC 27 PlayStation and Xbox share one transfer market; **PC is separate**. The
Iniesta gap above (2×) confirms console prices are not a usable proxy for PC.

## 2. Zidane test — what actually identifies a card version

Four FC 27 Zidane cards exist on FUT.GG. Two pairs are indistinguishable by the
obvious fields:

| | 1397 | 100664693 | 67110261 | 83887477 |
|---|---|---|---|---|
| version string | Base Icon | Base Icon **Pristine Holographic** | Debut International Icon | Debut International Icon **Holographic** |
| overall | 94 | 94 | 86 | 86 |
| position | CAM (alt CM) | CAM (alt CM) | CAM (alt CM) | CAM (alt CM) |
| rarityName | Base Icon | Base Icon | Debut International Icon | Debut International Icon |
| rarityEaId | 12 | 12 | 160 | 160 |
| raritySquadId | 46 | 562 | *null* | 353 |
| gradingScore | 45000 | 67500 | 4100 | 6150 |

**Identical across all four (22 fields):** name, position, alternativePositions,
club, league, nation, foot, weakFoot, skillMoves, height, age, isIcon, isHero,
isSpecial, isSbc, isObjective, lineColor, cardName, basePlayerEaId, …

**Conclusion:** name + rating + position is not enough, and **`rarityName` is not
enough either** — the holographic variants share it. The reliable identifiers are
`eaId` (always unique) and the human version string in the page's
`<meta name="description">`, which is the only field that spells out
"Holographic" / "Pristine Holographic". `raritySquadId` differs but is null on one
card, so it cannot stand alone.

The user's two example links (futbin 21491 / 21493) could not be read directly —
FUTBIN is unreachable. Search-engine titles show 21491 = "Zidane Icon EA FC 27 —
94" and 21959 = "— 86".

## 3. Card reading — vision vs local OCR

16 sample screenshots, 131×165 to 237×283 px. Ground truth hand-labelled in
`research/ground_truth.json`.

| engine | name | rating | position | all three | per image | card type |
|---|---|---|---|---|---|---|
| RapidOCR (ONNX) | 16/16 | 15/16 | 11/16 | **10/16** | 0.72 s | none |
| EasyOCR (torch) | 16/16 | 15/16 | 7/16 | **7/16** | 0.26 s | none |
| vision model | 16/16 | 16/16 | 16/16 | **16/16** | — | yes |

Representative OCR errors: `RM` → "RIM", `CM` → "CIM", `ST` → "15",
Zidane's **94 read as "6"** (RapidOCR), names glued ("KikaNazareth",
"LamineYamal"), position missing entirely on 5 of 16.

The decisive point is not accuracy but capability: **no OCR engine reports card
type at all.** Section 2 showed the discriminator between two same-rating cards
is "Holographic", which on the card is a *visual* property with no text to read.
Vision is the only option that can supply `card_type` and
`card_style_description`.

Not yet measured: Haiku 4.5 specifically, which needs an Anthropic API key.
Numbers above for "vision model" are from a direct read of the same 16 images.

---

# Follow-up measurements taken during implementation — 2026-09-20

## 4. Headless vs headful against FUTWIZ

Three sequential player pages, 6 s apart (the app's own pacing), fresh browser
profile each run:

```
headless: #1 OK 1.5s   #2 BLOCKED 25.8s   #3 BLOCKED 25.8s
headful : #1 OK 1.4s   #2 OK      1.2s    #3 OK      1.3s
```

Headless clears the bot check once and is then refused on every later load; a
normal window clears each one. The app therefore runs the price browser
headful by default (`BROWSER_HEADLESS=false`) with the window parked off-screen
(`BROWSER_OFFSCREEN=true`). No anti-detection patching is used.

## 5. How often FUTWIZ actually has a PC price

| Card | PC | Console |
|---|---|---|
| Mbappé 91 Rare | *unavailable* | 6 000 000 |
| Iniesta 92 Icon | 3 490 000 | 1 500 000 |
| Zidane 94 Icon | 6 000 000 | 2 869 000 |
| Zidane 94 Icon (2) | *unavailable* | 5 500 000 |
| Pelé 95 Icon | 8 999 000 | 6 960 000 |
| Ethan Mbappé 74 | no price block | — |

**3 of 6 sampled cards had a PC price.** Where FUTWIZ has none it prints
"Pricing unavailable at this time", which the provider reports as exactly that
rather than as a read failure. The PC/console gap on the cards that do have both
runs roughly 2x, which is why falling back to a console number without a loud
label would be worse than showing nothing.

## 6. End-to-end timings on the finished app

| Step | Measured |
|---|---|
| Catalog sitemap sync (18 786 players / 19 287 cards) | 12-15 s, one time |
| Folder watcher: file appears -> scan row | ~3 s |
| First price for a new card (FUTWIZ search + Card ID match + price page) | 16 s |
| Same card again (cache hit) | 0.15 s |
| Fallback to FUT.GG when FUTWIZ has no PC price | 25 s total |

FUTWIZ numbers cards itself, and its ids are not all large: Mbappé is
`/fc27/player/kylian-mbappe/27` while icons sit in the 111xxx range. The bridge
is the EA "Card ID" printed on every FUTWIZ player page, which equals FUT.GG's
`eaId`; the pair is cached permanently after the first lookup.

## 7. Local Ollama models

The installed `qwen3:30b-a3b` model reports only `completion`, `tools`, and
`thinking`; it does not report `vision`. It therefore cannot receive a card
screenshot. A direct image request also failed while loading the model because
CUDA could not allocate the requested ~14 GB buffer. Passing base64 pixels as
ordinary text would not add visual understanding, so it is not used as a fake
workaround.

The installed `qwen3.5:0.8b` does report `vision` and was measured on all 16
sample cards with thinking disabled:

| field | correct | speed |
|---|---:|---:|
| name | 13/16 | |
| rating | 16/16 | |
| position | 12/16 | |
| card type | 0/16 | |
| total | | median 4.4 s/image |

It labelled every card `hall_of_fut`, including bronze, silver, gold, TOTW and
Icon cards. Thinking mode was then tested on representative bronze, TOTW, Icon
and holographic-looking promo cards: card type remained **0/4**, while latency
increased to 4.2–13.7 seconds. The local `.env` therefore uses
`qwen3.5:0.8b` with `OLLAMA_THINK=false`. This is adequate for rating and often
for name/position, but exact artwork/version identification still requires the
candidate picker or a stronger vision-capable model.
