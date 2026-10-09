console.log("FC 27 VIP Sniper & SBC Çözücü Yüklendi!");

// Sayfaya inject.js dosyasini enjekte et
const script = document.createElement('script');
script.src = chrome.runtime.getURL('inject.js');
(document.head || document.documentElement).appendChild(script);

let currentSbcReq = null;
let currentSquadSolution = null;

// inject.js'den gelen verileri dinle
window.addEventListener('message', async function(event) {
    if (event.source !== window || !event.data) return;

    // SBC Sartlari geldi
    if (event.data.type === 'FC27_SBC_REQ') {
        currentSbcReq = event.data.data;
        console.log("VIP Asistan: SBC şartları alındı:", currentSbcReq);
        updateSbcUI();
    }

    // Kulup verisi geldiginde Python'a gonder!
    if (event.data.type === 'FC27_CLUB_DATA') {
        try {
            chrome.runtime.sendMessage({
                action: "fetch_api",
                url: 'http://127.0.0.1:8027/api/club/sync',
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: { items: event.data.items }
            }, (response) => {
                if (response && response.success) {
                    const d = response.data;
                    console.log("VIP Asistan: Kulüpten " + d.newly_added + " yeni oyuncu Python sunucusuna aktarıldı!");
                    const statusEl = document.getElementById("club-sync-status");
                    if(statusEl) statusEl.innerHTML = `<span style="color:#28a745">Kulüp Tarandı (${d.total_in_club} kart) ✅</span>`;
                } else {
                    console.error("Kulüp senkronizasyon hatasi:", response ? response.error : "Eklenti arka planına bağlanılamadı");
                }
            });
        } catch(e) {
            console.error("Mesaj gönderim hatası:", e);
        }
    }
});

function createPanel() {
    if (document.getElementById("fc27-vip-panel")) return;

    const panel = document.createElement("div");
    panel.id = "fc27-vip-panel";
    panel.innerHTML = `
        <div class="fc-header">🎯 VIP Asistan</div>
        <div id="fc-snipe-content" class="fc-body">
            <div id="club-sync-status" style="text-align:center; font-size:11px; color:#888; margin-bottom:10px; padding:5px; background:#111; border-radius:4px;">
                Kulüp Verisi Bekleniyor...<br>(Web App'te 'Kulüp' sekmesine tıkla)
            </div>

            <!-- SBC BÖLÜMÜ -->
            <div id="sbc-container" style="border: 1px solid #444; border-radius: 6px; padding: 10px; margin-bottom: 15px; background: #1a1a1a;">
                <h4 style="margin: 0 0 10px 0; color: #fbe08a; font-size: 14px;">🧠 Otomatik SBC</h4>
                <div id="sbc-status" style="font-size: 12px; color: #aaa; margin-bottom: 10px;">SBC sayfasına girildiğinde aktif olur.</div>

                <button id="btn-solve-sbc" style="display:none; width: 100%; padding: 8px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">
                    ✨ Kulüple Çöz
                </button>

                <div id="sbc-result" style="margin-top: 10px; font-size: 12px; display: none;">
                    <div style="margin-bottom: 5px; font-weight: bold; color: #fff;">Tahmini Maliyet: <span id="sbc-cost" style="color: #fbe08a;">0</span></div>
                    <ul id="sbc-players-list" style="list-style: none; padding: 0; margin: 0 0 10px 0; max-height: 150px; overflow-y: auto;">
                        <!-- Oyuncular buraya gelecek -->
                    </ul>
                    <button id="btn-fill-squad" style="width: 100%; padding: 8px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">
                        Kadroya Doldur (Konsept Dahil)
                    </button>
                </div>
            </div>

            <p>Sniper Durumu: <strong style="color:#28a745">Aktif</strong></p>
            <hr style="border-color:#444">
            <p><b>Kısayollar:</b></p>
            <ul style="font-size: 11px; padding-left: 15px;">
                <li><b>[ S ]</b>: Piyasa Ara</li>
                <li><b>[ Boşluk ]</b>: Hemen Al & Onayla</li>
            </ul>
        </div>
    `;
    document.body.appendChild(panel);

    // Olay Dinleyicileri Ekle
    document.getElementById("btn-solve-sbc").addEventListener("click", solveSBC);
    document.getElementById("btn-fill-squad").addEventListener("click", fillSquad);

    // Oynanabilirlik (Surukle Birak)
    makeDraggable(panel);
}

function makeDraggable(elmnt) {
    var pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
    var header = elmnt.querySelector('.fc-header');
    if (header) {
        header.style.cursor = 'move';
        header.onmousedown = dragMouseDown;
    } else {
        elmnt.onmousedown = dragMouseDown;
    }

    function dragMouseDown(e) {
        e = e || window.event;
        e.preventDefault();
        pos3 = e.clientX;
        pos4 = e.clientY;
        document.onmouseup = closeDragElement;
        document.onmousemove = elementDrag;
    }

    function elementDrag(e) {
        e = e || window.event;
        e.preventDefault();
        pos1 = pos3 - e.clientX;
        pos2 = pos4 - e.clientY;
        pos3 = e.clientX;
        pos4 = e.clientY;
        elmnt.style.top = (elmnt.offsetTop - pos2) + "px";
        elmnt.style.left = (elmnt.offsetLeft - pos1) + "px";
    }

    function closeDragElement() {
        document.onmouseup = null;
        document.onmousemove = null;
    }
}

function updateSbcUI() {
    if (!currentSbcReq) return;

    const statusEl = document.getElementById("sbc-status");
    const btnSolve = document.getElementById("btn-solve-sbc");

    if (statusEl && btnSolve) {
        statusEl.innerHTML = `Hedef: <b>${currentSbcReq.rating || 'Yok'} Reyting</b> | <b>${currentSbcReq.chem} Kimya</b>`;
        btnSolve.style.display = "block";
        document.getElementById("sbc-result").style.display = "none";
    }
}

async function solveSBC() {
    if (!currentSbcReq) return;

    const btnSolve = document.getElementById("btn-solve-sbc");
    btnSolve.textContent = "⏳ Hesaplanıyor...";
    btnSolve.disabled = true;

    try {
        chrome.runtime.sendMessage({
            action: "fetch_api",
            url: 'http://127.0.0.1:8027/api/sbc/solve',
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: {
                target_rating: currentSbcReq.rating || 0,
                min_chem: currentSbcReq.chem || 0,
                min_totw: currentSbcReq.totw || 0
            }
        }, (response) => {
            if (!response || !response.success) {
                alert("SBC Çözülemedi: " + (response ? response.error : "Bağlantı hatası"));
                btnSolve.textContent = "✨ Tekrar Dene";
                btnSolve.disabled = false;
                return;
            }

            const data = response.data;
            currentSquadSolution = data.squad;

            // UI Guncelle
            document.getElementById("sbc-result").style.display = "block";
            document.getElementById("sbc-cost").textContent = data.total_cost.toLocaleString();

            const listEl = document.getElementById("sbc-players-list");
            listEl.innerHTML = "";

            data.squad.forEach((p, index) => {
                const li = document.createElement("li");
                li.style.padding = "4px";
                li.style.borderBottom = "1px solid #333";
                li.style.display = "flex";
                li.style.justifyContent = "space-between";
                li.style.alignItems = "center";

                let nameDisplay = `<b>${p.rating}</b> ${p.name}`;
                if (p.is_concept) nameDisplay = `<span style="color:#007bff">[K]</span> ` + nameDisplay;
                if (p.is_untradeable) nameDisplay += ` <span style="color:#888; font-size:10px;">(Satılamaz)</span>`;

                li.innerHTML = `
                    <div style="flex:1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${nameDisplay}</div>
                    <button data-index="${index}" class="btn-remove-player" style="background:transparent; border:none; color:#dc3545; cursor:pointer; font-weight:bold;">X</button>
                `;
                listEl.appendChild(li);
            });

            // Cıkarma butonlarina event ekle
            document.querySelectorAll(".btn-remove-player").forEach(btn => {
                btn.addEventListener("click", function() {
                    const idx = this.getAttribute("data-index");
                    currentSquadSolution.splice(idx, 1);
                    this.parentElement.remove();
                });
            });

            btnSolve.textContent = "✅ Çözüldü!";
            setTimeout(() => {
                btnSolve.textContent = "✨ Yeniden Çöz";
                btnSolve.disabled = false;
            }, 2000);
        });

    } catch(e) {
        console.error("Solver Error:", e);
        alert("Mesaj gönderim hatası!");
        btnSolve.textContent = "✨ Kulüple Çöz";
        btnSolve.disabled = false;
    }
}

function fillSquad() {
    if (!currentSquadSolution || currentSquadSolution.length === 0) {
        alert("Kadro boş!");
        return;
    }

    // inject.js'e oyunculari Web App DOM'una eklemesi icin mesaj gonderiyoruz.
    // DOM manipülasyonu sayfa bağlamında olmalı, o yuzden content script'ten window.postMessage ile iletiyoruz.
    window.postMessage({
        type: 'FC27_FILL_SQUAD_COMMAND',
        squad: currentSquadSolution
    }, '*');

    const btn = document.getElementById("btn-fill-squad");
    btn.textContent = "⏳ Dolduruluyor...";
    setTimeout(() => { btn.textContent = "Kadroya Doldur (Konsept Dahil)"; }, 3000);
}

// Inatci yukleyici
let panelInterval = setInterval(() => {
    if (!document.getElementById("fc27-vip-panel") && document.body) {
        createPanel();
    } else if (document.getElementById("fc27-vip-panel")) {
        clearInterval(panelInterval);
    }
}, 2000);

// Keyboard Sniper
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    if (e.key === 's' || e.key === 'S') {
        const searchBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Search' || b.textContent.trim() === 'Ara');
        if (searchBtn) searchBtn.click();
    }

    if (e.key === ' ') {
        e.preventDefault();
        const buyBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Buy Now') || b.textContent.includes('Hemen Al'));
        if (buyBtn) {
            buyBtn.click();
            setTimeout(() => {
                const confirmBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Ok' || b.textContent.trim() === 'Tamam' || b.textContent.trim() === 'Evet');
                if (confirmBtn) confirmBtn.click();
            }, 350);
        }
    }
});
