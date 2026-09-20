/* FC 27 price tool — single-page client.
   Live updates arrive over SSE; everything else is a plain fetch.
   NOTE: API surface unchanged from the original; only presentation touched. */

const $ = (sel) => document.querySelector(sel);
const fmt = new Intl.NumberFormat("tr-TR");

const el = {
  dot: $("#live-dot"),
  stage: $("#stage"),
  empty: $("#empty"),
  watchDir: $("#watch-dir"),
  toggle: $("#watch-toggle"),
  watchLabel: $("#watch-label"),
  clipToggle: $("#clip-toggle"),
  clipLabel: $("#clip-label"),
  catalog: $("#catalog-info"),
  history: $("#history"),
  searchInput: $("#search-input"),
  searchBtn: $("#search-btn"),
  linkInput: $("#link-input"),
  linkBtn: $("#link-btn"),
  results: $("#search-results"),
  fixMsg: $("#fix-msg"),
  tpl: $("#card-tpl"),
  calcPanel: $("#calc-panel"),
  buyInput: $("#buy-input"),
  calcRes: $("#calc-res"),
  calcPl: $("#calc-pl"),
};

let current = null;              // the scan currently on stage
const scans = new Map();         // scan_id -> payload

/* ---------------------------------------------------------------- helpers */
function coins(value) {
  return value === null || value === undefined ? "—" : fmt.format(value);
}

function ago(seconds) {
  if (seconds === null || seconds === undefined) return "";
  if (seconds < 60) return `${seconds} sn önce`;
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m} dk önce`;
  return `${Math.round(m / 60)} sa önce`;
}

function setMsg(text, kind = "") {
  if (!el.fixMsg) return;
  el.fixMsg.textContent = text || "";
  el.fixMsg.className = `msg ${kind}`;
}

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
  return body;
}

/* -------------------------------------------------- state builders (DOM) */

function stateNode(kind, title, sub, extra) {
  const box = document.createElement("div");
  box.className = `empty state-${kind}`;
  box.dataset.testid = `state-${kind}`;

  if (kind === "loading" || kind === "waiting") {
    const ring = document.createElement("div");
    ring.className = "pulse-ring";
    ring.setAttribute("aria-hidden", "true");
    ring.innerHTML = "<span></span><span></span><span></span>";
    box.appendChild(ring);
  }

  const t = document.createElement("p");
  t.className = "state-title";
  t.textContent = title;
  box.appendChild(t);

  if (sub) {
    const s = document.createElement("p");
    s.className = "muted state-sub";
    s.textContent = sub;
    box.appendChild(s);
  }

  if (extra) box.appendChild(extra);
  return box;
}

/* ---------------------------------------------------------- rendering */
function renderCard(scan) {
  const node = el.tpl.content.cloneNode(true);
  const root = node.querySelector(".card-view");
  const card = scan.card;
  const price = scan.price;

  const img = root.querySelector(".art");
  const fallback = root.querySelector(".art-fallback");
  if (card?.image_url) {
    img.src = card.image_url;
    img.alt = `${card.name} ${card.rating}`;
    img.hidden = false;
    img.addEventListener("error", () => {
      img.hidden = true;
      fallback.hidden = false;
    }, { once: true });
    img.addEventListener("load", () => {
      fallback.remove();
    }, { once: true });
  }

  root.querySelector(".rating").textContent = card?.rating ?? "?";
  root.querySelector(".pname").textContent = card?.name ?? "Bilinmeyen";
  root.querySelector(".pos").textContent =
    [card?.position, ...(card?.alt_positions || [])].filter(Boolean).join(" / ") || "?";
  root.querySelector(".version").textContent = card?.version ?? "?";

  const priceEl = root.querySelector(".price");
  const netEl = root.querySelector(".net");
  const srcEl = root.querySelector(".src");
  const ageEl = root.querySelector(".age");
  const noteEl = root.querySelector(".note");
  const openEl = root.querySelector(".open");
  const coinDeco = root.querySelector(".coin");

  if (price && price.value !== null && price.value !== undefined) {
    priceEl.textContent = coins(price.value);
    netEl.textContent = coins(price.after_tax);
    srcEl.textContent = `${price.source} · ${price.platform.toUpperCase()}`;
    ageEl.textContent = ago(price.age_seconds);
    if (price.platform && price.platform !== "pc") {
      noteEl.textContent =
        "DİKKAT: bu KONSOL fiyatı, PC değil. PC piyasası ayrı ve fiyatlar farklı.";
      noteEl.className = "note warn small";
    } else if (price.note) {
      noteEl.textContent = price.note;
      noteEl.className = "note muted small";
    }
  } else {
    priceEl.textContent = price?.is_extinct ? "EXTINCT" : "Fiyat yok";
    priceEl.classList.add("none");
    netEl.textContent = "—";
    if (coinDeco) coinDeco.style.opacity = ".35";
    const why = (scan.failures || []).map((f) => `${f.source}: ${f.reason}`).join(" | ");
    noteEl.textContent = why || scan.message || "Fiyat alınamadı.";
    noteEl.className = "note bad small";
    // Boş/kaynağa özel satır bilgisi
    srcEl.textContent = price?.source ? `${price.source}` : "kaynak yok";
    ageEl.textContent = "";
  }

  if (price?.source_url) {
    openEl.href = price.source_url;
  } else if (card?.url) {
    openEl.href = card.url;
  } else {
    openEl.remove();
  }

  root.querySelector(".refresh").addEventListener("click", async (event) => {
    const btn = event.currentTarget;
    btn.disabled = true;
    const original = btn.innerHTML;
    btn.innerHTML = "Yenileniyor…";
    try {
      const updated = await api(`/api/scans/${scan.scan_id}/refresh`, { method: "POST" });
      show(updated);
    } catch (err) {
      setMsg(err.message, "err");
    } finally {
      btn.disabled = false;
      btn.innerHTML = original;
    }
  });

  return root;
}

function renderCandidates(scan, container, note) {
  container.innerHTML = "";

  const wrap = document.createElement("div");
  wrap.className = "panel";
  wrap.dataset.testid = "candidates-panel";

  if (note) {
    const p = document.createElement("p");
    p.className = "pick-note";
    p.textContent = note;
    wrap.appendChild(p);
  }

  const head = document.createElement("header");
  head.className = "panel-head compact";
  head.innerHTML = `
    <span class="eyebrow">Birden fazla eşleşme</span>
    <h2>Hangi kart bu?</h2>
    <p class="muted small">Holographic ve normal versiyonları karşılaştır, doğru olanı seç.</p>
  `;
  wrap.appendChild(head);

  const list = document.createElement("div");
  list.className = "candidates";
  for (const card of scan.candidates || []) {
    list.appendChild(candidateNode(card, scan.scan_id));
  }
  wrap.appendChild(list);

  container.appendChild(wrap);
}

function candidateNode(card, scanId) {
  const node = document.createElement("button");
  node.className = "cand";
  node.type = "button";
  node.dataset.testid = "candidate-item";

  if (card.image_url) {
    const img = new Image();
    img.src = card.image_url;
    img.alt = "";
    img.loading = "lazy";
    img.addEventListener("error", () => {
      const ph = document.createElement("div");
      ph.className = "ph";
      ph.textContent = "?";
      img.replaceWith(ph);
    }, { once: true });
    node.appendChild(img);
  } else {
    const ph = document.createElement("div");
    ph.className = "ph";
    ph.textContent = "?";
    node.appendChild(ph);
  }

  const name = document.createElement("b");
  name.textContent = `${card.rating ?? "?"} · ${card.name}`;
  node.appendChild(name);

  const meta = document.createElement("span");
  meta.textContent = `${card.position ?? "?"} · ${card.version ?? "?"}`;
  node.appendChild(meta);

  node.addEventListener("click", async () => {
    if (scanId === null || scanId === undefined) {
      setMsg("Önce bir tarama seç, sonra kartı seç.", "err");
      return;
    }
    node.disabled = true;
    setMsg("Kaydediliyor…");
    try {
      const updated = await api(`/api/scans/${scanId}/correct`, {
        method: "POST",
        body: JSON.stringify({ ea_id: card.ea_id }),
      });
      show(updated);
      el.results.innerHTML = "";
      setMsg("Kaydedildi. Bu görsel bir daha sorulmayacak.", "ok");
    } catch (err) {
      setMsg(err.message, "err");
    } finally {
      node.disabled = false;
    }
  });

  return node;
}

function show(scan) {
  current = scan;
  scans.set(scan.scan_id, scan);
  el.stage.innerHTML = "";

  if (scan.status === "matched" && scan.card) {
    el.stage.appendChild(renderCard(scan));
    if (scan.price && scan.price.value !== null && scan.price.value !== undefined) {
      el.calcPanel.hidden = false;
      const storedBuy = localStorage.getItem(`buy_${scan.card.ea_id}`);
      el.buyInput.value = storedBuy || "";
      refreshCalcView();
    } else {
      el.calcPanel.hidden = true;
    }
  } else if (scan.status === "ambiguous") {
    renderCandidates(
      scan,
      el.stage,
      scan.message || "Birden fazla kart eşleşti — hangisi olduğunu seç.",
    );
    el.calcPanel.hidden = true;
  } else {
    let title = "Hata";
    let sub = scan.message || "";
    if (scan.status === "not_a_card") { title = "Görsel bir kart değil"; sub = scan.message || "Bu görselde FC kartı bulunamadı, atlandı."; }
    else if (scan.status === "no_match") { title = "Kart bulunamadı"; sub = scan.message || "Kataloğunda eşleşen kart yok. Sağdan manuel arayabilirsin."; }

    const extra = document.createDocumentFragment();
    if (scan.reading?.name) {
      const read = document.createElement("p");
      read.className = "muted small";
      read.style.marginTop = "8px";
      read.textContent =
        `Okunan: ${scan.reading.name} · ${scan.reading.rating ?? "?"} · ` +
        `${scan.reading.position ?? "?"} · ${scan.reading.card_type ?? "?"}`;
      extra.appendChild(read);
    }

    el.stage.appendChild(stateNode(scan.status || "error", title, sub, extra));
    el.calcPanel.hidden = true;
  }

  renderHistory();
}

function renderHistory() {
  // History UI is intentionally hidden per design brief.
  // We still keep the map + DOM node so downstream code paths keep working.
  if (!el.history) return;
  el.history.innerHTML = "";
  const rows = [...scans.values()].sort((a, b) => b.scan_id - a.scan_id).slice(0, 25);
  for (const scan of rows) {
    const li = document.createElement("li");
    li.dataset.scanId = scan.scan_id;
    li.addEventListener("click", () => show(scan));
    el.history.appendChild(li);
  }
}

function refreshCalcView() {
  if (!current || !current.price || current.price.value === null || current.price.value === undefined) return;
  const buyPrice = parseInt(el.buyInput.value, 10);
  const eaId = current.card.ea_id;

  if (isNaN(buyPrice) || buyPrice <= 0) {
    el.calcRes.hidden = true;
    localStorage.removeItem(`buy_${eaId}`);
    return;
  }
  localStorage.setItem(`buy_${eaId}`, buyPrice);
  const pl = current.price.after_tax - buyPrice;
  el.calcRes.hidden = false;
  el.calcRes.className = "calc-res " + (pl > 0 ? "profit" : (pl < 0 ? "loss" : ""));
  el.calcPl.textContent = (pl > 0 ? "+" : "") + coins(pl);
}

/* ------------------------------------------------------------ actions */
async function runSearch() {
  const query = el.searchInput.value.trim();
  if (query.length < 2) {
    setMsg("En az 2 harf yaz.", "err");
    return;
  }
  el.searchBtn.disabled = true;
  setMsg("Aranıyor…");
  try {
    const { results } = await api(`/api/search?q=${encodeURIComponent(query)}`);
    el.results.innerHTML = "";
    if (!results.length) {
      setMsg("Sonuç yok.", "err");
      return;
    }
    const list = document.createElement("div");
    list.className = "candidates";
    for (const card of results) list.appendChild(candidateNode(card, current?.scan_id));
    el.results.appendChild(list);
    setMsg(
      current ? "Doğru kartı tıkla." : "Önce bir tarama gelsin, sonra kartı tıkla.",
      current ? "ok" : "err",
    );
  } catch (err) {
    setMsg(err.message, "err");
  } finally {
    el.searchBtn.disabled = false;
  }
}

async function addLink() {
  const url = el.linkInput.value.trim();
  if (!url) return;
  el.linkBtn.disabled = true;
  setMsg("Ekleniyor…");
  try {
    const body = { url, scan_id: current?.scan_id ?? null };
    const result = await api("/api/link", { method: "POST", body: JSON.stringify(body) });
    if (result.scan_id) {
      show(result);
      setMsg("Kart eklendi ve bu taramaya bağlandı.", "ok");
    } else {
      setMsg(`Katalog'a eklendi: ${result.card.rating} ${result.card.name}`, "ok");
    }
    el.linkInput.value = "";
  } catch (err) {
    setMsg(err.message, "err");
  } finally {
    el.linkBtn.disabled = false;
  }
}

async function setCapture(path, enabled, apply) {
  try {
    apply(await api(path, { method: "POST", body: JSON.stringify({ enabled }) }));
  } catch (err) {
    setMsg(err.message, "err");
  }
}

function applyWatchStatus(status) {
  if (!status || status.enabled === undefined) return;
  el.toggle.checked = status.enabled;
  el.watchLabel.textContent = status.enabled ? "Klasör izleme açık" : "İzleme duraklatıldı";
  el.watchDir.textContent =
    (status.directory || "—") + (status.directory_exists === false ? " ⚠ klasör yok" : "");
  if (status.last_error) setMsg(status.last_error, "err");
}

function applyClipStatus(status) {
  if (!status || status.enabled === undefined) return;
  el.clipToggle.checked = status.enabled;
  el.clipLabel.textContent = status.enabled ? "Pano açık" : "Pano";
}

/* --------------------------------------------------------------- boot */
function connect() {
  const source = new EventSource("/api/events");

  source.addEventListener("hello", () => el.dot.classList.add("on"));
  source.addEventListener("scan", (event) => show(JSON.parse(event.data)));
  source.addEventListener("watcher", (event) => applyWatchStatus(JSON.parse(event.data)));
  source.addEventListener("clipboard", (event) => applyClipStatus(JSON.parse(event.data)));
  source.addEventListener("catalog", (event) => {
    const data = JSON.parse(event.data);
    el.catalog.textContent =
      data.players ? `katalog · ${fmt.format(data.players)} oyuncu` : `katalog · ${data.status}`;
  });

  source.onerror = () => {
    el.dot.classList.remove("on");
    // EventSource retries on its own; no manual reconnect needed.
  };
}

async function boot() {
  try {
    const status = await api("/api/status");
    applyWatchStatus(status.watcher);
    applyClipStatus(status.clipboard);
    el.catalog.textContent = status.catalog.players
      ? `katalog · ${fmt.format(status.catalog.players)} oyuncu`
      : `katalog · ${status.catalog.status}`;
    if (!status.vision?.ready) {
      setMsg(status.vision?.error || "Görsel okuma modeli hazır değil.", "err");
    }
  } catch (err) {
    setMsg(err.message, "err");
  }

  try {
    const { scans: rows } = await api("/api/scans");
    for (const row of rows.reverse()) scans.set(row.scan_id, row);
    const newest = [...scans.values()].sort((a, b) => b.scan_id - a.scan_id)[0];
    if (newest) show(newest); else renderHistory();
  } catch { /* history is optional on first run */ }

  connect();
}

/* --------------------------------------------------------------- wire */
el.toggle.addEventListener("change", (e) =>
  setCapture("/api/watch", e.target.checked, applyWatchStatus));
el.clipToggle.addEventListener("change", (e) =>
  setCapture("/api/clipboard", e.target.checked, applyClipStatus));
el.searchBtn.addEventListener("click", runSearch);
el.searchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") runSearch(); });
el.searchInput.addEventListener("search", runSearch);
el.linkBtn.addEventListener("click", addLink);
el.linkInput.addEventListener("keydown", (e) => { if (e.key === "Enter") addLink(); });
el.buyInput.addEventListener("input", refreshCalcView);

boot();
