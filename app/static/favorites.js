async function loadFavorites() {
    const container = document.getElementById('fav-container');
    try {
        const res = await fetch('/api/favorites');
        const data = await res.json();

        if (data.favorites.length === 0) {
            container.innerHTML = `<p style="color:var(--muted); text-align:center; grid-column: 1 / -1; margin-top: 40px;">Favorilerinizde henüz kimse yok. Ana sayfadan veya Telegram'dan (/takip) oyuncu ekleyebilirsiniz.</p>`;
            return;
        }

        container.innerHTML = '';
        data.favorites.forEach(f => {
            const isUp = f.pct_change > 0;
            const changeClass = isUp ? 'change-up' : 'change-down';
            const sign = isUp ? '+' : '';

            const card = document.createElement('div');
            card.className = 'fav-card';
            card.innerHTML = `
                <div class="fav-header">
                    <div>
                        <span class="fav-rating">${f.rating}</span>
                        <span class="fav-name">${f.name}</span>
                    </div>
                    <button class="remove-btn" onclick="toggleFav(${f.ea_id}, '${f.name}', ${f.rating})">Kaldır</button>
                </div>
                <div class="fav-price-box">
                    <div class="fav-old-price">Dün: ${f.old_price.toLocaleString('tr-TR')} 🪙</div>
                    <div class="fav-current-price">${f.current_price.toLocaleString('tr-TR')} 🪙</div>
                    <div class="fav-change ${changeClass}">${sign}${f.pct_change}%</div>
                </div>
                <div class="fav-advice" style="background-color: ${f.advice_color};">
                    ${f.advice}
                </div>
            `;
            container.appendChild(card);
        });

    } catch(e) {
        container.innerHTML = `<p style="color:#ff4444; text-align:center; grid-column: 1 / -1; margin-top: 40px;">Hata oluştu.</p>`;
    }
}

async function toggleFav(ea_id, name, rating) {
    await fetch('/api/favorites/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ea_id, name, rating })
    });
    loadFavorites();
}

document.addEventListener('DOMContentLoaded', loadFavorites);
