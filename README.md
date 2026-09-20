# FC 27 Fiyat Aracı

Oyunda bir kart görürsün, ekran görüntüsünü alırsın, tarayıcıdaki sayfada saniyeler
içinde **PC piyasasındaki en düşük BIN fiyatı** ve %5 vergi sonrası eline geçecek
tutarı görürsün. Local çalışır, Windows için.

- Klasör izleme (yeni ekran görüntüsü) **veya** pano (Win+Shift+S) ile yakalama
- Kartı seçtiğin görsel model okur: Anthropic veya yerel Ollama
- Aynı görsel iki kez işlenmez, kart olmayan görüntüler sessizce atlanır
- Birden fazla kart eşleşirse kart görselleriyle sorar, seçimini kalıcı hatırlar
- Fiyat çekilemese bile kart ve **sebebi** gösterilir

---

## Kurulum (tek komut)

Gereken: Windows 10/11 ve [Python 3.11+](https://www.python.org/downloads/)
("Add Python to PATH" işaretli kurulmalı).

```powershell
.\start.ps1
```

veya `start.bat` dosyasına çift tıkla. İlk çalıştırma sanal ortamı kurar,
bağımlılıkları ve Playwright'ın Chromium'unu indirir, `.env.example`'ı `.env`
olarak kopyalar. Sonraki çalıştırmalar doğrudan sunucuyu açar
(http://127.0.0.1:8027).

İlk çalıştırmadan sonra `.env` dosyasını aç. Kartı kim okuyacak, onu seç:

```ini
# Bulut (ücretli, en doğru)
VISION_BACKEND=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# veya local (ücretsiz, Ollama)
VISION_BACKEND=ollama
OLLAMA_MODEL=qwen3.5:0.8b

WATCH_DIR=C:\Users\etemk\Pictures\Screenshots
```

Anthropic anahtarını https://console.anthropic.com/settings/keys adresinden
alırsın. İkisi de olmadan uygulama yine açılır; sadece kart okuma kapalı kalır.

Sanal ortamı sıfırlamak için: `.\start.ps1 -Recreate`

---

## Kullanım

1. Sayfayı aç (http://127.0.0.1:8027).
2. Sağ üstten **Otomatik izleme** ve/veya **Pano**'yu aç.
3. Oyunda kartın ekran görüntüsünü al (veya Win+Shift+S ile kopyala).
4. Kart, fiyat ve vergi sonrası tutar sayfada belirir.

Yanlış kart çıktıysa alttaki kutudan oyuncu adını ara ya da FUT.GG kart linkini
yapıştır, doğru kartı tıkla. O görsel bir daha sorulmaz.

**Uygulama açılmadan önce klasörde duran dosyalar işlenmez** — sadece açıldıktan
sonra gelenler.

---

## Fiyat kaynakları: neden böyle

Kodlamadan önce dört kaynak ölçüldü (`research/FINDINGS.md` ham sonuçlar ve
ölçüm betikleriyle birlikte duruyor). Özet:

| Kaynak | Düz `httpx` | Gerçek tarayıcı | PC fiyatı |
|---|---|---|---|
| FUTBIN | 403 Cloudflare (`robots.txt` dahil) | 15.5 sn sonra hâlâ challenge | — |
| FUT.GG | 200, metadata tam SSR | fiyat 1.2 sn'de geliyor | **yok, sadece `ps5`** |
| FUTWIZ | 403 Cloudflare | aralıklı geçiyor, ~1.5 sn | **var** |
| FUTDatabase | 401 (key gerekli) | — | var ama **premium, €79/ay** |

İki sonuç mimariyi belirledi:

1. **FC 27'de PC ayrı bir transfer marketi** (PS ve Xbox ortak). Fark kozmetik
   değil: Iniesta 92 Icon ölçümünde konsol **1.370.000**, PC **2.850.000**.
   Bu yüzden birincil kaynak FUTWIZ (PC). FUT.GG yedek olarak duruyor ama
   döndürdüğü fiyat arayüzde açıkça **"KONSOL fiyatı, PC değil"** diye
   işaretlenir.
2. **FUTBIN kullanılmıyor.** Her isteğe Cloudflare duvarı çıkıyor, headless
   tarayıcı da geçemiyor. Geçmek için bot korumasını aktif olarak kırmak
   gerekirdi; yapılmadı. Bu yüzden FUTBIN linki yapıştırırsan uygulama
   "okuyamıyorum" der ve seni aramaya yönlendirir.

FUT.GG'nin fiyat ucu (`/api/fut/player-prices/...?verify=<imza>`) hem
robots.txt'te kapalı hem imzalı; o imza akışı taklit edilmiyor. Katalog için
sadece robots'un açık bıraktığı `/players/...` sayfaları ve crawler'lar için
yayınlanan sitemap kullanılıyor.

### Tarayıcı neden görünür (headless değil)

Ölçüm: headless Chromium FUTWIZ'in bot kontrolünü **bir kez** geçiyor, sonraki
her yüklemede takılıyor. Normal bir pencere her seferinde ~1.3 sn'de geçiyor.

```
headless: #1:OK 1.5s   #2:BLK 25.8s  #3:BLK 25.8s
headful : #1:OK 1.4s   #2:OK   1.2s  #3:OK   1.3s
```

Bu yüzden `BROWSER_HEADLESS=false` varsayılan. Pencere `BROWSER_OFFSCREEN=true`
ile ekran dışına park edilir, oyun oynarken odağı çalmaz. Bot koruması
kırılmıyor — sadece normal bir tarayıcı kullanılıyor.

### FUTWIZ'de PC fiyatı her kartta yok

Örneklenen 6 kartın 3'ünde PC fiyatı vardı; diğerlerinde FUTWIZ kendisi
"Pricing unavailable at this time" diyor. Ölçüm:

| Kart | PC | Konsol |
|---|---|---|
| Mbappé 91 Rare | yok | 6.000.000 |
| Iniesta 92 Icon | 3.490.000 | 1.500.000 |
| Zidane 94 Icon | 6.000.000 | 2.869.000 |
| Zidane 94 Icon (2) | yok | 5.500.000 |
| Pelé 95 Icon | 8.999.000 | 6.960.000 |

PC yoksa uygulama konsol fiyatına düşer ve **açıkça uyarır**. Fark 2 katına
çıkabildiği için bu uyarı önemli — sessizce konsol fiyatı göstermek, fiyat
göstermemekten kötü olurdu.

**Kaynaklara nazik davranılıyor:** aynı anda tek sayfa yüklenir, yüklemeler
arasında en az `BROWSER_MIN_INTERVAL` saniye beklenir, çerezler kalıcı tarayıcı
profilinde tutulur, fiyatlar `PRICE_CACHE_TTL` boyunca önbellekte kalır. Toplu
kazıma yok — katalog sen kart taradıkça organik büyür.

---

## Kart kimliği: Zidane problemi

Aynı oyuncunun onlarca kartı var ve **isim yetmez**. FC 27'de dört Zidane var;
ikisi şu alanların **hepsinde** aynı:

| | `27-1397` | `27-100664693` |
|---|---|---|
| isim | Zinedine Zidane | Zinedine Zidane |
| rating | 94 | 94 |
| pozisyon | CAM (alt: CM) | CAM (alt: CM) |
| `rarityName` | Base Icon | Base Icon |
| `rarityEaId` | 12 | 12 |
| **versiyon** | Base Icon | Base Icon **Pristine Holographic** |

Yani **kart tipi bile ayırt etmiyor**. Tek güvenilir kimlik `eaId`. Uygulama
kartları hep `eaId` ile saklar; isim + rating + pozisyon sadece adayları
daraltır, iki aday kalırsa kart görselleriyle sana sorar. Seçimin görselin
algısal hash'ine (dHash) bağlanır, aynı kartın başka boyuttaki görüntüsünde de
hatırlanır.

---

## Yapı

```
app/
  main.py                  FastAPI + lifespan, servisleri bağlar
  core/
    config.py              .env tabanlı ayarlar
    db.py                  SQLite motoru (WAL), session yönetimi
    events.py              SSE olay veriyolu
    logging.py             log formatı
    state.py               süreç genelindeki tekil nesneler
  models/
    tables.py              SQLModel tabloları
    schemas.py             kalıcı olmayan veri nesneleri
  routers/
    system.py              durum, SSE, izleme anahtarları
    scans.py               tarama geçmişi, düzeltme, fiyat yenileme
    catalog.py             arama, link ekleme, sitemap senkronu
  services/
    scan_service.py        boru hattı: görsel -> kart -> fiyat
    repository.py          tüm veritabanı erişimi
    ingest/folder.py       klasör izleme (dosya tamamlanmasını bekler)
    ingest/clipboard.py    pano yakalama
    recognize/vision.py    Claude görsel okuma (katı araç şeması)
    recognize/imaging.py   hash'ler ve görsel hazırlama
    catalog/futgg.py       FUT.GG sitemap + sayfa parser
    catalog/serial.py      FUT.GG'nin gömülü JS state okuyucusu
    matching/normalize.py  isim/pozisyon/rating normalizasyonu
    matching/matcher.py    fuzzy eşleştirme ve aday daraltma
    matching/links.py      yapıştırılan linkten kart kimliği
    prices/base.py         PriceProvider arayüzü
    prices/browser.py      paylaşılan, nazik Playwright havuzu
    prices/futwiz.py       PC fiyatı (birincil)
    prices/futgg.py        konsol fiyatı (yedek)
    prices/chain.py        önbellek + yedek zinciri
    prices/registry.py     kaynakların bağlandığı tek yer
  static/                  tek sayfa arayüz
research/                  kodlama öncesi ölçümler + FINDINGS.md
tests/                     191 test, ağ mock'lu
```

---

## Yeni bir fiyat kaynağı eklemek

Bir kaynak kırılırsa **tek dosya** değişir. Üç adım:

**1. Provider'ı yaz** — `app/services/prices/base.py` içindeki `PriceProvider`
protokolünü karşılasın:

```python
# app/services/prices/mysite.py
from datetime import datetime, timezone

from ...models.schemas import PriceQuote
from ...models.tables import CatalogCard
from .base import PriceUnavailable


class MySiteProvider:
    name = "mysite"
    platform = "pc"          # "pc" veya "console" -- arayüz bunu gösterir

    def __init__(self, pool, repo) -> None:
        self._pool = pool    # Playwright gerekmiyorsa kullanma
        self._repo = repo

    async def fetch(self, card: CatalogCard) -> PriceQuote:
        price = ...          # card.ea_id ile fiyatı bul
        if price is None:
            # Sessizce yutma: sebebi söyle, zincir bir sonrakine geçsin.
            raise PriceUnavailable(self.name, "Sayfada fiyat yok.")
        return PriceQuote(
            ea_id=card.ea_id,
            price=price,
            platform=self.platform,
            source=self.name,
            fetched_at=datetime.now(timezone.utc),
            source_url="https://...",
        )

    async def aclose(self) -> None:
        return None
```

**2. Kaydet** — `app/services/prices/registry.py` içinde tek satır:

```python
BUILDERS = {
    "futwiz": lambda pool, repo: FutwizProvider(pool, repo),
    "futgg":  lambda pool, repo: FutGGPriceProvider(pool),
    "mysite": lambda pool, repo: MySiteProvider(pool, repo),   # <-- yeni
}
```

**3. Sıraya koy** — `.env`:

```ini
PRICE_PROVIDERS=mysite,futwiz,futgg
```

İlk başarılı kaynak kazanır; başarısız olanların sebepleri arayüzde listelenir.
Hepsi başarısız olursa bayat önbellek değeri yaşıyla birlikte gösterilir.

Bir siteyi HTML'den okuyorsan `BrowserPool.open()` kullan (tek seferde tek
sayfa, otomatik tempo, challenge beklemesi); düz HTTP yetiyorsa `httpx` kullan
ve `pool`'u hiç açma — daha hızlı ve daha az yük.

---

## Ayarlar (`.env`)

| Anahtar | Varsayılan | Ne işe yarar |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Kart okuma için gerekli |
| `VISION_MODEL` | `claude-haiku-4-5` | Küçük ve ucuz; yanlış okursa büyüt |
| `WATCH_DIR` | `%USERPROFILE%\Pictures\Screenshots` | İzlenen klasör |
| `WATCH_EXTENSIONS` | `.png,.jpg,.jpeg` | Alınacak uzantılar |
| `CLIPBOARD_ENABLED` | `true` | Pano yakalama |
| `PRICE_PROVIDERS` | `futwiz,futgg` | Kaynak sırası |
| `PRICE_CACHE_TTL` | `420` | Fiyatın taze sayıldığı süre (sn) |
| `BROWSER_MIN_INTERVAL` | `6.0` | İki sayfa yüklemesi arası en az bekleme |
| `BROWSER_CHALLENGE_TIMEOUT` | `25.0` | Bot doğrulaması için sabır süresi |
| `BROWSER_HEADLESS` | `false` | Görünür pencere; headless FUTWIZ'de engelleniyor |
| `BROWSER_OFFSCREEN` | `true` | O pencereyi ekran dışına park et |
| `EA_TAX_RATE` | `0.05` | EA satış vergisi |
| `HOST` / `PORT` | `127.0.0.1` / `8027` | Sunucu adresi |

---

## Testler

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

214 test, tamamı ağsız: FUT.GG parser'ı kaydedilmiş gerçek sayfalarla, HTTP
katmanı `respx` ile mock'lu, fiyat zinciri sahte provider'larla çalışır.
Kapsam: isim normalizasyonu (Türkçe/aksan), link'ten ID çıkarma, eşleştirme ve
aday daraltma, dosya tamamlanma beklemesi, dedupe, düzeltme hafızası, önbellek
ve yedek zinciri, PC/konsol fiyat seçimi.

---

## Sorun giderme

**"Görsel okuma kapalı"** — Anthropic seçiliyse `.env` içinde
`ANTHROPIC_API_KEY` yoktur; Ollama seçiliyse servis kapalıdır veya model
`vision` yeteneğine sahip değildir.

**"Bot doğrulaması geçilemedi"** — FUTWIZ ardışık isteklerde sıkıyor. Birkaç
dakika bekle; `BROWSER_MIN_INTERVAL`'i artırmak kalıcı çözüm.

**"İzlenen klasör yok"** — `WATCH_DIR` yanlış. Windows'ta oyun içi ekran
görüntüleri genelde `%USERPROFILE%\Videos\Captures` veya
`%USERPROFILE%\Pictures\Screenshots` altında olur.

**Katalog boş** — ilk açılışta FUT.GG sitemap'i indirilir (~21.000 kart, birkaç
saniye). `POST /api/catalog/sync?force=true` ile yeniden tetiklenir.

**"FUTWIZ bu kart için PC fiyatı yayınlamıyor"** — hata değil, FUTWIZ'in
kendi ifadesi. Uygulama konsol fiyatına düşer ve uyarıyı gösterir.

**Fiyat yok ama kart doğru** — kart extinct olabilir, ya da FUTWIZ o an
erişilemiyordur. Sebep kartın altında yazar; "Fiyatı yenile" ile tekrar dene.

---

## Bilinçli sınırlar

- Sadece **PC** fiyatı hedeflenir; konsol fiyatı sadece yedek olarak ve açık
  uyarıyla gösterilir.
- EA'nın resmî olmayan web app uçları **kullanılmaz** (hesap ban riski).
- Bot korumaları aşılmaya çalışılmaz.
- Toplu katalog kazıma yapılmaz.
- Bir ekran görüntüsünde birden fazla kart varsa en belirgin olanı okunur.
