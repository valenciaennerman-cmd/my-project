let squad = new Array(11).fill(null);
let slots = [];
let activeSlot = null;

const pitch = document.getElementById('pitch-container');
const formSelect = document.getElementById('formation-select');

// Search elements
const searchInput = document.createElement('input');
searchInput.type = 'text';
searchInput.placeholder = 'Oyuncu Ara (Örn: 89 messi)...';
searchInput.className = 'buy-input';
searchInput.style.width = '100%';
searchInput.style.marginBottom = '20px';

const searchRes = document.createElement('div');
searchRes.style.background = 'var(--surface-2)';
searchRes.style.padding = '10px';
searchRes.style.borderRadius = '8px';
searchRes.style.display = 'none';
searchRes.style.flexDirection = 'column';
searchRes.style.gap = '10px';

const panel = document.querySelector('.panel');
panel.insertBefore(searchRes, document.querySelector('#formation-select').parentElement);
panel.insertBefore(searchInput, searchRes);

function parseFormation(fmtStr) {
    // E.g. "4-3-3(2)" -> [4, 3, 3]
    let base = fmtStr.split('(')[0];
    let parts = base.split('-');
    // Reverse because we render from top to bottom (Attackers to Defenders)
    return parts.map(n => parseInt(n)).reverse();
}

function renderPitch(fmtStr) {
    // Keep the background logo
    pitch.innerHTML = `<div style="text-align:center; color: #fff; opacity:0.1; font-weight:bold; position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); pointer-events: none; font-size: 40px; z-index:0;">FC 27</div>`;

    const rows = parseFormation(fmtStr);
    // Add GK row at the end
    rows.push(1);

    let slotIndex = 0;
    slots = [];

    rows.forEach(count => {
        const rowDiv = document.createElement('div');
        rowDiv.style.display = 'flex';
        rowDiv.style.justifyContent = 'center';
        rowDiv.style.gap = '40px';
        rowDiv.style.zIndex = '2';

        for(let i=0; i<count; i++) {
            const currentIdx = slotIndex;
            const slot = document.createElement('div');
            slot.className = 'slot';

            // Re-apply existing player if exists
            if (squad[currentIdx]) {
                const c = squad[currentIdx];
                slot.innerHTML = `
                    <img src="${c.image_url}" style="width:100%; height:100%; object-fit:cover; border-radius:8px; opacity:0.8;">
                    <div style="position:absolute; bottom:5px; background:rgba(0,0,0,0.8); width:100%; text-align:center; font-size:12px;">${c.rating} ${c.position}</div>
                `;
                slot.style.border = '2px solid var(--gold)';
            } else {
                slot.innerText = "+"; // Empty slot placeholder
            }

            slot.addEventListener('click', () => {
                activeSlot = currentIdx;
                searchInput.focus();
                searchInput.placeholder = "Bu pozisyon için oyuncu ara...";
                slots.forEach(s => s.style.boxShadow = 'none');
                slot.style.boxShadow = '0 0 10px var(--gold)';
            });

            slots.push(slot);
            rowDiv.appendChild(slot);
            slotIndex++;
        }
        pitch.appendChild(rowDiv);
    });
}

formSelect.addEventListener('change', () => {
    // We could clear squad, or just let them stay in their indices.
    // For now, keep squad to avoid annoying the user, but render new slots.
    renderPitch(formSelect.value);
});

renderPitch(formSelect.value);

searchInput.addEventListener('keydown', async (e) => {
    if (e.key === 'Enter') {
        const query = searchInput.value.trim();
        if (!query) return;

        searchRes.innerHTML = 'Aranıyor...';
        searchRes.style.display = 'flex';

        try {
            const res = await fetch('/api/search?q=' + encodeURIComponent(query));
            const data = await res.json();

            searchRes.innerHTML = '';
            if(!data.results || data.results.length === 0) {
                searchRes.innerHTML = 'Sonuç bulunamadı.';
                return;
            }

            data.results.slice(0, 5).forEach(card => {
                const btn = document.createElement('button');
                btn.className = 'btn ghost';
                btn.style.textAlign = 'left';
                btn.style.display = 'flex';
                btn.style.flexDirection = 'column';
                btn.style.gap = '4px';

                let smwf = (card.skill_moves ? card.skill_moves+"★ SM" : "Yakında SM") + " / " + (card.weak_foot ? card.weak_foot+"★ WF" : "Yakında WF");
                let alt = card.alt_positions && card.alt_positions.length > 0 ? card.alt_positions.join(", ") : "";

                btn.innerHTML = `
                    <div style="font-weight:bold; color:var(--text-main);">${card.rating} ${card.name} (${card.position})</div>
                    <div style="font-size:12px; color:var(--muted);">${alt} | ${smwf}</div>
                `;

                btn.onclick = () => {
                    if (activeSlot !== null) {
                        squad[activeSlot] = card;
                        renderPitch(formSelect.value); // Re-render to update image
                        activeSlot = null;
                        searchRes.style.display = 'none';
                        searchInput.value = '';
                        searchInput.placeholder = 'Oyuncu Ara (Örn: 89 messi)...';
                        updateStats();
                    } else {
                        alert("Lütfen önce sahadan boş bir pozisyon (artı işareti) seçin!");
                    }
                };
                searchRes.appendChild(btn);
            });
        } catch(e) {
            searchRes.innerHTML = 'Arama hatası. Sunucu çalışmıyor olabilir.';
        }
    }
});

function updateStats() {
    let totalRating = 0;
    let count = 0;

    // Chemistry counters
    let clubs = {};
    let leagues = {};
    let nations = {};

    squad.forEach(c => {
        if (c) {
            totalRating += c.rating;
            count++;

            if (c.club_name) clubs[c.club_name] = (clubs[c.club_name] || 0) + 1;
            if (c.league_name) leagues[c.league_name] = (leagues[c.league_name] || 0) + 1;
            if (c.nation_name) nations[c.nation_name] = (nations[c.nation_name] || 0) + 1;
        }
    });
    const avg = count > 0 ? Math.round(totalRating / count) : 0;

    // Calculate Chemistry
    let totalChem = 0;
    squad.forEach(c => {
        if (!c) return;
        let pChem = 0;

        let cCount = clubs[c.club_name] || 0;
        let lCount = leagues[c.league_name] || 0;
        let nCount = nations[c.nation_name] || 0;

        // FC Thresholds
        if (cCount >= 7) pChem += 3;
        else if (cCount >= 4) pChem += 2;
        else if (cCount >= 2) pChem += 1;

        if (lCount >= 8) pChem += 3;
        else if (lCount >= 5) pChem += 2;
        else if (lCount >= 3) pChem += 1;

        if (nCount >= 8) pChem += 3;
        else if (nCount >= 5) pChem += 2;
        else if (nCount >= 2) pChem += 1;

        // Max 3 per player
        if (pChem > 3) pChem = 3;

        // Icons and Heroes have special rules, but this is the base logic
        totalChem += pChem;
    });

    if (totalChem > 33) totalChem = 33;

    const strongs = document.querySelectorAll('.panel > div strong');
    if (strongs.length >= 3) {
        if (count === 11) {
            strongs[0].innerText = avg;
            strongs[1].innerText = totalChem + "/33";
            strongs[2].innerText = "Hesaplanıyor 🪙"; // Wait, I should try to calculate price!
        } else {
            strongs[0].innerText = count + "/11 Oyuncu";
            strongs[1].innerText = totalChem + "/33 (Geçici)";
            strongs[2].innerText = "Kadro Eksik";
        }
    }
}
