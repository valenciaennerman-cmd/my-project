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
  historyPanel: $("#history-panel"),
  historyCount: $("#history-count"),
  chartPanel: $("#chart-panel"),
  chartTitle: $("#chart-title"),
  chartWrap: $("#chart-wrap"),
  chartNote: $("#chart-note"),
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

const STATUS_LABEL = {
  not_a_card: "kart değil",
  no_match: "bulunamadı",
  ambiguous: "seçim bekliyor",
  error: "hata",
  pending: "işleniyor",
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
  loadChart();
}

function renderHistory() {
  if (!el.history) return;
  const rows = [...scans.values()].sort((a, b) => b.scan_id - a.scan_id).slice(0, 25);

  if (el.historyPanel) el.historyPanel.hidden = rows.length === 0;
  if (el.historyCount) el.historyCount.textContent = rows.length ? `${rows.length} kayıt` : "";

  el.history.innerHTML = "";
  for (const scan of rows) {
    el.history.appendChild(historyRow(scan));
  }
}

function historyRow(scan) {
  const li = document.createElement("li");
  li.className = "h-row";
  li.dataset.scanId = scan.scan_id;
  li.dataset.testid = "history-row";
  if (current && scan.scan_id === current.scan_id) li.classList.add("is-current");

  const time = document.createElement("span");
  time.className = "h-time";
  time.textContent = new Date(scan.created_at).toLocaleTimeString("tr-TR", {
    hour: "2-digit", minute: "2-digit",
  });

  const thumb = document.createElement("span");
  thumb.className = "h-thumb";
  if (scan.card && scan.card.image_url) {
    const img = document.createElement("img");
    img.src = scan.card.image_url;
    img.alt = "";
    img.loading = "lazy";
    img.addEventListener("error", () => img.remove(), { once: true });
    thumb.appendChild(img);
  }

  const main = document.createElement("span");
  main.className = "h-main";
  const title = document.createElement("span");
  title.className = "h-name";
  const sub = document.createElement("span");
  sub.className = "h-sub muted";

  if (scan.card) {
    title.textContent = `${scan.card.rating} ${scan.card.name}`;
    sub.textContent = scan.card.version || "";
  } else {
    title.textContent = (scan.reading && scan.reading.name) || scan.image_name || "—";
    sub.textContent = scan.message || "";
    const tag = document.createElement("span");
    tag.className = `h-tag tag-${scan.status}`;
    tag.textContent = STATUS_LABEL[scan.status] || scan.status;
    title.appendChild(tag);
  }
  main.append(title, sub);

  const price = document.createElement("span");
  price.className = "h-price";
  if (scan.price && scan.price.value !== null && scan.price.value !== undefined) {
    price.textContent = coins(scan.price.value);
    if (scan.price.platform !== "pc") price.classList.add("is-console");
  }

  li.append(time, thumb, main, price);
  li.addEventListener("click", () => show(scan));
  return li;
}


function refreshCalcView() {
  if (!current || !current.price || current.price.value === null || current.price.value === undefined) return;
  const buyPrice = parseInt(el.buyInput.value, 10);
  const eaId = current.card.ea_id;

  if (isNaN(buyPrice) || buyPrice <= 0) {
    el.calcRes.hidden = true;
    localStorage.removeItem(`buy_${eaId}`);
    drawChart();
    return;
  }
  localStorage.setItem(`buy_${eaId}`, buyPrice);
  const pl = current.price.after_tax - buyPrice;
  el.calcRes.hidden = false;
  el.calcRes.className = "calc-res " + (pl > 0 ? "profit" : (pl < 0 ? "loss" : ""));
  el.calcPl.textContent = (pl > 0 ? "+" : "") + coins(pl);
  // buy price drives the baseline and the profit band
  drawChart();
}


/* ---------------------------------------------------------------- chart */
/* Price history, drawn as inline SVG. The series is only what this app has
   actually observed -- no background polling, no third-party history mixed in,
   so every point is a real PC reading taken while you were using the tool. */

const CHART = {
  range: "24h",
  series: { bin: true, net: true, buy: true, pl: false },
  data: null,
  eaId: null,
};

const RANGE_LABEL = { "1h": "son 1 saat", "24h": "son 24 saat", "7d": "son 7 gün" };

function buyPriceFor(eaId) {
  try {
    const value = parseInt(localStorage.getItem(`buy_${eaId}`), 10);
    return Number.isFinite(value) && value > 0 ? value : null;
  } catch {
    return null; // private mode / blocked storage
  }
}

async function loadChart() {
  if (!el.chartPanel) return;
  const card = current && current.card;
  if (!card) {
    el.chartPanel.hidden = true;
    return;
  }
  CHART.eaId = card.ea_id;
  el.chartPanel.hidden = false;
  el.chartTitle.textContent = `${card.rating} ${card.name}`;

  try {
    CHART.data = await api(`/api/cards/${card.ea_id}/history?range=${CHART.range}`);
  } catch (err) {
    CHART.data = null;
    el.chartWrap.innerHTML = "";
    el.chartNote.textContent = err.message;
    el.chartNote.className = "chart-note small is-err";
    return;
  }
  drawChart();
}

function drawChart() {
  const data = CHART.data;
  if (!data) return;

  const buy = buyPriceFor(CHART.eaId);
  const points = data.points.map((p) => ({
    t: new Date(p.t).getTime(), bin: p.bin, net: p.net,
  }));

  el.chartNote.className = "chart-note muted small";

  if (points.length < 2) {
    el.chartWrap.innerHTML = "";
    el.chartWrap.appendChild(chartEmpty(points.length, data.total_recorded));
    el.chartNote.textContent = data.total_recorded
      ? `Toplam ${data.total_recorded} kayıt var, ${RANGE_LABEL[CHART.range]} içinde ${data.in_range}.`
      : "Fiyat çektikçe burası dolar — arka planda otomatik örnekleme yapılmıyor.";
    return;
  }

  el.chartWrap.innerHTML = "";
  el.chartWrap.appendChild(
    CHART.series.pl && buy ? plChart(points, buy) : priceChart(points, buy)
  );

  const last = points[points.length - 1];
  const parts = [`${points.length} nokta · ${RANGE_LABEL[CHART.range]}`];
  if (buy) {
    const pl = last.net - buy;
    parts.push(`şu an ${pl >= 0 ? "kâr" : "zarar"}: ${pl >= 0 ? "+" : ""}${coins(pl)}`);
  } else {
    parts.push("alış fiyatını yazarsan kâr/zarar da çizilir");
  }
  el.chartNote.textContent = parts.join(" · ");
}

function chartEmpty(inRange, total) {
  const box = document.createElement("div");
  box.className = "chart-empty";
  box.dataset.testid = "chart-empty";
  const title = document.createElement("p");
  title.className = "state-title";
  title.textContent =
    inRange === 0 ? "Bu aralıkta kayıt yok" : "Grafik için en az 2 nokta gerekli";
  const sub = document.createElement("p");
  sub.className = "muted small";
  sub.textContent = total
    ? `Toplam ${total} fiyat kaydı var. Başka bir aralık dene ya da "Fiyatı yenile"ye bas.`
    : 'Her "Fiyatı yenile"de bir nokta eklenir.';
  box.append(title, sub);
  return box;
}

/* ---- geometry ---- */
const PAD = { top: 16, right: 14, bottom: 24, left: 66 };
const VIEW = { w: 900, h: 260 };

function niceTicks(min, max, count = 4) {
  if (min === max) return [min];
  const step = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step)));
  const norm = step / mag;
  const nice = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
  const out = [];
  for (let v = Math.ceil(min / nice) * nice; v <= max + 1e-9; v += nice) out.push(v);
  return out.length ? out : [min, max];
}

function svgEl(name, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

function makeSvg() {
  const svg = svgEl("svg", {
    viewBox: `0 0 ${VIEW.w} ${VIEW.h}`,
    class: "chart-svg",
    role: "img",
  });
  svg.dataset.testid = "chart-svg";
  return svg;
}

function scales(points, lo, hi) {
  const t0 = points[0].t;
  const span = (points[points.length - 1].t - t0) || 1;
  const range = (hi - lo) || 1;
  return {
    x: (t) => PAD.left + ((t - t0) / span) * (VIEW.w - PAD.left - PAD.right),
    y: (v) => PAD.top + (1 - (v - lo) / range) * (VIEW.h - PAD.top - PAD.bottom),
  };
}

function linePath(points, key, sc) {
  return points
    .map((p, i) => `${i ? "L" : "M"}${sc.x(p.t).toFixed(1)} ${sc.y(p[key]).toFixed(1)}`)
    .join(" ");
}

function addGrid(svg, ticks, sc, format) {
  for (const value of ticks) {
    const y = sc.y(value);
    svg.appendChild(svgEl("line", {
      x1: PAD.left, x2: VIEW.w - PAD.right, y1: y, y2: y, class: "grid-line",
    }));
    const label = svgEl("text", {
      x: PAD.left - 10, y: y + 4, class: "axis-label", "text-anchor": "end",
    });
    label.textContent = format(value);
    svg.appendChild(label);
  }
}

function addTimeAxis(svg, points, sc) {
  const first = points[0].t;
  const last = points[points.length - 1].t;
  const spansDays = new Date(first).toDateString() !== new Date(last).toDateString();

  const fmt = (ms) => {
    const d = new Date(ms);
    if (CHART.range === "7d") {
      return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit" });
    }
    const time = d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
    return spansDays
      ? `${d.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit" })} ${time}`
      : time;
  };

  const ticks = [
    [first, "start"],
    [first + (last - first) / 2, "middle"],
    [last, "end"],
  ];
  for (const [ms, anchor] of ticks) {
    const label = svgEl("text", {
      x: anchor === "start" ? PAD.left
        : anchor === "end" ? VIEW.w - PAD.right
        : sc.x(ms),
      y: VIEW.h - 6, class: "axis-label", "text-anchor": anchor,
    });
    label.textContent = fmt(ms);
    svg.appendChild(label);
  }
}

function shortCoins(value) {
  const abs = Math.abs(value);
  if (abs >= 1e6) return (value / 1e6).toFixed(abs >= 1e7 ? 0 : 1).replace(".", ",") + "M";
  if (abs >= 1e3) return Math.round(value / 1e3) + "K";
  return String(Math.round(value));
}

/* ---- price view: BIN + after-tax lines, buy price as a baseline,
        and the gap between after-tax and buy shaded -- that gap is the profit */
function priceChart(points, buy) {
  const values = [];
  if (CHART.series.bin) values.push(...points.map((p) => p.bin));
  if (CHART.series.net) values.push(...points.map((p) => p.net));
  if (CHART.series.buy && buy) values.push(buy);
  if (!values.length) values.push(...points.map((p) => p.bin));

  let lo = Math.min(...values);
  let hi = Math.max(...values);
  const pad = ((hi - lo) || hi || 1) * 0.12;
  lo -= pad;
  hi += pad;

  const sc = scales(points, lo, hi);
  const svg = makeSvg();
  addGrid(svg, niceTicks(lo, hi), sc, shortCoins);

  if (CHART.series.buy && CHART.series.net && buy) {
    const top = linePath(points, "net", sc);
    const back = points
      .slice()
      .reverse()
      .map((p) => `L${sc.x(p.t).toFixed(1)} ${sc.y(buy).toFixed(1)}`)
      .join(" ");
    const profitable = points[points.length - 1].net >= buy;
    svg.appendChild(svgEl("path", {
      d: `${top} ${back} Z`,
      class: `band ${profitable ? "band-profit" : "band-loss"}`,
    }));
  }

  if (CHART.series.buy && buy) {
    svg.appendChild(svgEl("line", {
      x1: PAD.left, x2: VIEW.w - PAD.right,
      y1: sc.y(buy), y2: sc.y(buy), class: "line-buy",
    }));
  }
  if (CHART.series.bin) {
    svg.appendChild(svgEl("path", { d: linePath(points, "bin", sc), class: "line-bin" }));
  }
  if (CHART.series.net) {
    svg.appendChild(svgEl("path", { d: linePath(points, "net", sc), class: "line-net" }));
  }

  const last = points[points.length - 1];
  if (CHART.series.bin) {
    svg.appendChild(svgEl("circle", {
      cx: sc.x(last.t), cy: sc.y(last.bin), r: 4, class: "dot-bin",
    }));
  }
  addTimeAxis(svg, points, sc);
  return svg;
}

/* ---- profit/loss view: its own zero baseline, so the scale stays readable ---- */
function plChart(points, buy) {
  const pl = points.map((p) => ({ t: p.t, v: p.net - buy }));
  let lo = Math.min(0, ...pl.map((p) => p.v));
  let hi = Math.max(0, ...pl.map((p) => p.v));
  const pad = ((hi - lo) || Math.abs(hi) || 1) * 0.15;
  lo -= pad;
  hi += pad;

  const sc = scales(points, lo, hi);
  const svg = makeSvg();
  addGrid(svg, niceTicks(lo, hi), sc, (v) => (v > 0 ? "+" : "") + shortCoins(v));

  const zero = sc.y(0);
  svg.appendChild(svgEl("line", {
    x1: PAD.left, x2: VIEW.w - PAD.right, y1: zero, y2: zero, class: "zero-line",
  }));

  const path = pl
    .map((p, i) => `${i ? "L" : "M"}${sc.x(p.t).toFixed(1)} ${sc.y(p.v).toFixed(1)}`)
    .join(" ");
  const close =
    `L${sc.x(pl[pl.length - 1].t).toFixed(1)} ${zero} L${sc.x(pl[0].t).toFixed(1)} ${zero} Z`;
  const profitable = pl[pl.length - 1].v >= 0;

  svg.appendChild(svgEl("path", {
    d: path + close, class: `band ${profitable ? "band-profit" : "band-loss"}`,
  }));
  svg.appendChild(svgEl("path", {
    d: path, class: `line-pl ${profitable ? "is-profit" : "is-loss"}`,
  }));
  svg.appendChild(svgEl("circle", {
    cx: sc.x(pl[pl.length - 1].t), cy: sc.y(pl[pl.length - 1].v), r: 4,
    class: `dot-pl ${profitable ? "is-profit" : "is-loss"}`,
  }));
  addTimeAxis(svg, points, sc);
  return svg;
}

function bindChartControls() {
  for (const btn of document.querySelectorAll(".range-btn")) {
    btn.addEventListener("click", () => {
      CHART.range = btn.dataset.range;
      for (const other of document.querySelectorAll(".range-btn")) {
        other.classList.toggle("is-on", other === btn);
      }
      loadChart();
    });
  }
  for (const chip of document.querySelectorAll(".chip[data-series]")) {
    chip.addEventListener("click", () => {
      const key = chip.dataset.series;
      CHART.series[key] = !CHART.series[key];
      chip.classList.toggle("is-on", CHART.series[key]);
      drawChart();
    });
  }
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

bindChartControls();
boot();
