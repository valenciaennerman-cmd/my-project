# FC 27 Fiyat Aracı — Frontend Redesign

## Original problem statement
EA FC 27 kartlarının fiyatını ekran görüntüsünden bulan, Windows local Python/FastAPI backend'i olan web uygulamasının FRONTEND arayüzü yeniden tasarımı. Backend'e (API, SSE, veri modelleri) dokunmadan yalnızca `app/static/index.html` + `style.css` + `app.js` güncellenecek.

## User choices
- Koyu antrasit + sıcak altın vurgu (premium companion app)
- Manrope + Sora + Space Grotesk (numeric tabular)
- Sol: manuel düzeltme, Sağ: büyük kart + fiyat. Son taramalar UI'da gösterilmiyor.
- Backend API'ye bağlı kalan üretim kodu + ayrı preview.html demo
- Framework yok — düz HTML/CSS/JS

## What's been implemented (2026-02)
- /app/static/index.html — top bar (canlı, klasör izleme, pano), 2 kolon layout, kart template, calc-box, hidden history
- /app/static/style.css — CSS token sistemi (renk/boşluk/radius/gölge/tipografi), tüm durum stilleri, responsive breakpoints, reduced-motion
- /app/static/app.js — mevcut API + SSE davranışı birebir korundu; sadece durum rendering + toast/mesaj metinleri iyileştirildi
- /app/static/preview.html — 5 durumun (empty, matched, ambiguous, no-price, no-match) mock önizlemesi

## API surface (dokunulmadı)
- GET  /api/status
- GET  /api/scans
- GET  /api/search?q=
- POST /api/link
- POST /api/scans/{id}/refresh
- POST /api/scans/{id}/correct
- POST /api/watch
- POST /api/clipboard
- SSE  /api/events (hello, scan, watcher, clipboard, catalog)

## Backlog / P1
- Kompakt son taramalar şeridi (isteğe bağlı, şu an hidden)
- Skeleton loading (fiyat yükleniyor) için ayrı geçiş
- Klavye kısayolları: R = yenile, F = arama odak
