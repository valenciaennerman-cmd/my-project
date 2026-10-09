// Bu dosya dogrudan EA Web App sayfasinin icine (window objesine) enjekte edilecek.
(function() {
    console.log("FC 27 VIP: Kulüp Sniffer Aktif!");

    const XHR = XMLHttpRequest.prototype;
    const open = XHR.open;
    const send = XHR.send;

    XHR.open = function(method, url) {
        this._url = url;
        return open.apply(this, arguments);
    };

    XHR.send = function() {
        this.addEventListener('load', function() {
            if (this._url && this._url.includes('/sbc/challenge')) {
                try {
                    const data = JSON.parse(this.responseText);
                    let reqs = { rating: null, chem: 0, totw: 0 };

                    if (data.requirements) {
                        data.requirements.forEach(r => {
                            const rStr = JSON.stringify(r).toUpperCase();

                            // Reyting
                            if (rStr.includes('RATING') && r.val >= 70 && r.val <= 95) {
                                reqs.rating = r.val;
                            }
                            // Kimya
                            if (rStr.includes('CHEMISTRY') && r.val > 0) {
                                reqs.chem = r.val;
                            }
                            // TOTW (Team of the week / IF)
                            if (rStr.includes('TOTW') || rStr.includes('TEAM OF THE WEEK') || (rStr.includes('RARITY') && rStr.includes('GROUP'))) {
                                if(r.val > 0 && r.val < 11) reqs.totw = r.val;
                            }
                        });
                    }
                    if (reqs.rating || reqs.chem > 0 || reqs.totw > 0) {
                        window.postMessage({ type: 'FC27_SBC_REQ', data: reqs }, '*');
                        console.log("FC 27 VIP: SBC Görev Şartları havada yakalandı!", reqs);
                    }
                } catch(e) {}
            }

            if (this._url && (this._url.includes('/ut/game/fc27/club') || this._url.includes('/ut/game/fc25/club'))) {
                try {
                    const data = JSON.parse(this.responseText);
                    if (data && data.itemData) {
                        const items = data.itemData.map(item => ({
                            ea_id: item.assetId || item.defId, // defId is base id
                            instance_id: item.id == null ? null : String(item.id),
                            item_score: item.itemScore || 0,
                            untradeable: item.untradeable || false
                        }));

                        // Send data to content.js
                        window.postMessage({
                            type: 'FC27_CLUB_DATA',
                            items: items
                        }, '*');

                        console.log("FC 27 VIP: Kulüpten " + items.length + " oyuncu yakalandı!");
                    }
                } catch(e) {}
            }
        });
        return send.apply(this, arguments);
    };

    // Modern Fetch API icin de override (Fifa bazen fetch kullaniyor)
    const originalFetch = window.fetch;
    window.fetch = async function() {
        const response = await originalFetch.apply(this, arguments);
        const url = arguments[0];

        if (url && (url.includes('/ut/game/fc27/club') || url.includes('/ut/game/fc25/club'))) {
            response.clone().json().then(data => {
                if (data && data.itemData) {
                    const items = data.itemData.map(item => ({
                        ea_id: item.assetId || item.defId,
                        instance_id: item.id == null ? null : String(item.id),
                        item_score: item.itemScore || 0,
                        untradeable: item.untradeable || false
                    }));
                    window.postMessage({ type: 'FC27_CLUB_DATA', items: items }, '*');
                }
            }).catch(e => {});
        }
        return response;
    };

    // Dinleyici: content.js'den gelen "Kadroya Doldur" emri
    window.addEventListener('message', async function(event) {
        if (event.source !== window || !event.data) return;

        if (event.data.type === 'FC27_FILL_SQUAD_COMMAND') {
            const squad = event.data.squad;
            console.log("VIP Asistan: Kadro Doldurma Komutu Alındı!", squad);

            // Gercek EA Web App uzerinde DOM manipulasyonu (Bot)
            // Bu kod parcalari EA'in o anki React DOM agacina baglidir, arayuz degisirse class'lar guncellenmelidir.
            alert("SBC Doldurucu başlatılıyor. Lütfen fareye dokunmayın...");

            try {
                // 1. Kadrodaki boş slotlari bul
                const slots = Array.from(document.querySelectorAll('.ut-squad-slot-view')).filter(slot => !slot.classList.contains('has-player'));

                if (slots.length === 0) {
                    console.log("Bos slot bulunamadi!");
                    return;
                }

                // Demo / Güvenli mod simulasyonu:
                // Gercek oyuncu eklemek icin EA WebApp servislerine (ut/game/fc27/squad)
                // internal api cagrisi yapmak (services.Squad.addPlayer) en saglamidir ama obfuscate edilmistir.
                // UI uzerinden tiklayarak yapmak:
                for (let i = 0; i < Math.min(squad.length, slots.length); i++) {
                    const player = squad[i];
                    console.log(`Slot ${i} -> ${player.name} (${player.rating}) yerlestirilecek.`);

                    // Slot'a tikla
                    // slots[i].click();

                    // Arama menusune EA_ID veya Isim yaz
                    // add delay vs...
                }

                console.log("Kadro yerleştirme tamamlandi (Simülasyon Bitti).");

            } catch(e) {
                console.error("Doldurma hatasi:", e);
            }
        }
    });

})();
