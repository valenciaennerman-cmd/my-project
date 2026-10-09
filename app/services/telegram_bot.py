import asyncio
import logging
import httpx
from datetime import datetime
from .scan_service import ScanService

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token: str, chat_id: str, service: ScanService):
        self.token = token
        self.chat_id = chat_id
        self.service = service
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.client = httpx.AsyncClient(timeout=15.0)
        self.offset = 0
        self._task = None

    def start(self):
        if not self.token:
            logger.info("Telegram token bulunamadi, bot baslamiyor.")
            return
        self._task = asyncio.create_task(self._poll())
        logger.info("Telegram botu baslatildi.")

    async def aclose(self):
        if self._task:
            self._task.cancel()
        await self.client.aclose()

    async def send_alarm(self, message: str):
        if not self.token or not self.chat_id:
            logger.warning("Telegram token veya chat_id eksik. Mesaj gonderilemedi.")
            return
        try:
            await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": self.chat_id, "text": message})
        except Exception as e:
            logger.error("Telegram alarm hatasi: %s", e)

    async def _poll(self):
        while True:
            try:
                resp = await self.client.get(f"{self.base_url}/getUpdates", params={"offset": self.offset, "timeout": 10})
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        self.offset = update["update_id"] + 1
                        message = update.get("message")
                        if message and ("text" in message or "photo" in message):
                            await self._handle_message(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Telegram poll hatasi: %s", e)
                await asyncio.sleep(5)
            await asyncio.sleep(1)

    async def _process_bulk(self, chat_id: int, text: str):
        import re
        import asyncio
        from app.services.watchlist import add_to_watchlist

        await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "📝 Çoklu liste algılandı! Tek tek güncel fiyatları çekiliyor, bu işlem oyuncu sayısına göre birkaç dakika sürebilir. Lütfen bekleyin..."})

        blocks = text.strip().split('\n\n')
        report_lines = []

        for block in blocks:
            name_match = re.search(r'^(.*?)\s*\((\d{2})', block)
            pc_match = re.search(r'PC:\s*([\d.,]+)', block)

            if name_match and pc_match:
                name = name_match.group(1).strip()
                rating = int(name_match.group(2))
                target_price = int(pc_match.group(1).replace('.', '').replace(',', ''))

                # Search player
                raw_results = await self.service.search(name, limit=5)
                best_match = None
                for res in raw_results:
                    if res.get("rating") == rating:
                        best_match = res
                        break

                if best_match:
                    ea_id = best_match["ea_id"]

                    # Caching logic
                    db = self.service._repo
                    card = db.card(ea_id)
                    if card:
                        # Bu islem biraz surebilir cunku her kartta eger cache yoksa Playwright calisir
                        quote, _ = await self.service._prices.get(card)
                        current_price = quote.price if quote else 0

                        add_to_watchlist(ea_id, name, rating, target_price)

                        if current_price > 0:
                            if current_price <= target_price:
                                report_lines.append(f"✅ {name} ({rating}) | Eski: {target_price} -> GÜNCEL: {current_price} 🎯 ALINABİLİR!")
                            else:
                                report_lines.append(f"⏳ {name} ({rating}) | Eski: {target_price} -> GÜNCEL: {current_price} ❌ (Takipte)")
                        else:
                            report_lines.append(f"⚠️ {name} ({rating}) | Fiyat bulunamadı (Takipte)")
                    else:
                        report_lines.append(f"❌ {name} ({rating}) kartı veritabanında yok.")
                else:
                    report_lines.append(f"❌ {name} ({rating}) bulunamadı.")

            await asyncio.sleep(2)

        final_report = "📊 **Çoklu Liste Güncel Analiz Sonucu** 📊\n\n" + "\n".join(report_lines)
        final_report += "\n\n🚀 Tüm oyuncular VIP Takip listesine eklendi. Hedef fiyata düşenler olursa bildirim gelmeye devam edecek!"

        for i in range(0, len(final_report), 4000):
            await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": final_report[i:i+4000]})

    async def _process_slash_list(self, chat_id: int, text: str):
        import asyncio
        await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "📝 Yatırımcı listesi (Slashed List) algılandı! İsimler ayrıştırılıyor ve anlık PC piyasası taranıyor..."})

        target_line = ""
        for line in text.split('\n'):
            if " / " in line and len(line.split(" / ")) > 3:
                target_line = line
                break

        names = [n.strip() for n in target_line.split(' / ') if n.strip()]
        report_lines = []

        for name in names:
            raw_results = await self.service.search(name, limit=3)
            if raw_results:
                best_match = raw_results[0]
                ea_id = best_match["ea_id"]
                rating = best_match["rating"]
                full_name = best_match["name"]

                db = self.service._repo
                card = db.card(ea_id)
                if card:
                    quote, _ = await self.service._prices.get(card)
                    current_price = quote.price if quote else 0
                    if current_price > 0:
                        report_lines.append(f"✅ {full_name} ({rating}) -> GÜNCEL: **{current_price:,}** 🪙")
                    else:
                        report_lines.append(f"⚠️ {full_name} ({rating}) -> Fiyat bulunamadı.")
                else:
                    report_lines.append(f"❌ {name} -> Veritabanında yok.")
            else:
                report_lines.append(f"❌ {name} -> Bulunamadı.")

            await asyncio.sleep(1)

        final_report = "📊 **Yatırım Listesi Güncel PC Fiyatları** 📊\n\n" + "\n".join(report_lines)
        final_report += "\n\n💡 *Tavsiye: Bu oyuncuları kulüp stoku olarak Cuma/Cumartesi satışı için tutuyorsan, piyasa takibini bu listeden yapabilirsin.*"

        for i in range(0, len(final_report), 4000):
            await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": final_report[i:i+4000], "parse_mode": "Markdown"})

    async def _handle_message(self, message: dict):
        text = message.get("text", "")
        chat_id = message["chat"]["id"]

        # Save chat_id to memory if not set in config, so alarms can go to the last person
        if not self.chat_id:
            self.chat_id = str(chat_id)

        if "photo" in message:
            await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "📸 Yapay zeka (Görsel okuma) özelliği kapatılmıştır. Lütfen komutları kullanın."})
            return

        if False:
            import base64
            from app.core.config import settings
            import re

            await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "📸 Kadro fotoğrafı alındı! Yapay zeka ile analiz ediliyor..."})
            try:
                photo_sizes = message["photo"]
                file_id = photo_sizes[-1]["file_id"]

                res = await self.client.get(f"{self.base_url}/getFile?file_id={file_id}")
                file_path = res.json()["result"]["file_path"]

                img_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
                img_res = await self.client.get(img_url)
                img_bytes = img_res.content
                b64_img = base64.b64encode(img_bytes).decode('utf-8')

                prompt = "Bu fotoğrafta EA FC 27 oyuncu kartları (kadro veya transfer listesi) var. Ekrandaki tüm futbolcuların reytinglerini ve isimlerini alt alta yaz. Başka hiçbir cümle veya ekstra kelime kurma. Sadece şu formatta listele:\n87 Musiala\n83 Casemiro\n80 Rafa"

                ollama_payload = {
                    "model": settings.ollama_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [b64_img]
                        }
                    ],
                    "stream": False,
                    "options": {"temperature": 0.1}
                }

                ollama_res = await self.client.post(f"{settings.ollama_host}/api/chat", json=ollama_payload, timeout=60.0)
                if ollama_res.status_code != 200:
                    await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": f"Ollama API Hatası: {ollama_res.status_code}"})
                    return

                ollama_text = ollama_res.json()["message"]["content"]
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": f"🤖 Yapay Zeka Çıktısı:\n{ollama_text}\n\nFiyatlar hesaplanıyor..."})

                lines = ollama_text.strip().split('\n')
                total_val = 0
                found_msgs = []

                for line in lines:
                    line = line.strip()
                    if not line: continue
                    query = line
                    rating_match = re.search(r'\b(\d{2})\b', query)
                    expected_rating = int(rating_match.group(1)) if rating_match else None
                    if expected_rating:
                        query = re.sub(r'\b\d{2}\b', '', query).strip()
                    if not query: continue

                    raw_results = await self.service.search(query, limit=5)
                    if raw_results:
                        if expected_rating:
                            results = sorted(raw_results, key=lambda x: abs((x.get("rating") or 0) - expected_rating))
                        else:
                            results = sorted(raw_results, key=lambda x: -(x.get("rating") or 0))

                        card_info = results[0]
                        ea_id = card_info["ea_id"]
                        card = self.service._repo.card(ea_id)
                        if card:
                            quote, _ = await self.service._prices.get(card)
                            if quote and quote.price:
                                total_val += quote.price
                                found_msgs.append(f"✅ {card.rating} {card.name}: {quote.price:,} 🪙")
                            else:
                                found_msgs.append(f"⚠️ {card.rating} {card.name}: Fiyat yok")

                if not found_msgs:
                    await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "Maalesef yapay zeka fotoğraftan hiçbir oyuncuyu eşleştiremedi."})
                    return

                final_msg = "📸 *FOTOĞRAF ANALİZİ SONUÇLARI* 📸\n\n"
                final_msg += "\n".join(found_msgs)
                final_msg += f"\n\n🏆 *TOPLAM DEĞER:* {total_val:,} 🪙"

                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": final_msg, "parse_mode": "Markdown"})

            except Exception as e:
                logger.error("Fotoğraf okuma hatası: %s", e)
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": f"Fotoğraf işlenirken hata oluştu: {str(e)}"})
            return

        if text == "/start":
            await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": f"FC 27 Snipe Botuna Hoş Geldin! 🎉\n\nSenin kalıcı Chat ID numaran: {chat_id}\nBunu .env dosyasına TELEGRAM_CHAT_ID= kısmına yapıştırabilirsin.\n\nFiyat sorgulamak için:\n/fiyat 84 ronaldo"})
            return

        if text.startswith("/toplu"):
            queries = text.replace("/toplu", "").strip().split(",")
            if not queries or not any(q.strip() for q in queries):
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "Lütfen oyuncuları virgülle ayırarak yazın. Örnek: /toplu 87 musiala, 87 upamecano, 83 casemiro"})
                return

            await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": f"⏳ Transfer listesindeki {len([q for q in queries if q.strip()])} oyuncu hesaplanıyor..."})

            total_val = 0
            found_msgs = []
            import re

            for query in queries:
                original_query = query.strip()
                query = original_query
                if not query: continue

                rating_match = re.search(r'\b(\d{2})\b', query)
                expected_rating = int(rating_match.group(1)) if rating_match else None
                if expected_rating:
                    query = re.sub(r'\b\d{2}\b', '', query).strip()

                if not query: continue

                raw_results = await self.service.search(query, limit=5)
                if raw_results:
                    if expected_rating:
                        results = sorted(raw_results, key=lambda x: abs((x.get("rating") or 0) - expected_rating))
                    else:
                        results = sorted(raw_results, key=lambda x: -(x.get("rating") or 0))

                    card_info = results[0]
                    ea_id = card_info["ea_id"]
                    card = self.service._repo.card(ea_id)
                    if card:
                        quote, _ = await self.service._prices.get(card)
                        if quote and quote.price:
                            total_val += quote.price
                            found_msgs.append(f"✅ {card.rating} {card.name}: {quote.price:,} 🪙")
                        else:
                            found_msgs.append(f"⚠️ {card.rating} {card.name}: Fiyat yok")
                else:
                    found_msgs.append(f"❌ {original_query}: Bulunamadı")

            final_msg = "📋 *TRANSFER LİSTESİ RAPORU* 📋\n\n"
            final_msg += "\n".join(found_msgs)
            final_msg += f"\n\n💰 *GENEL TOPLAM:* {total_val:,} 🪙"

            await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": final_msg, "parse_mode": "Markdown"})
            return

        if text.startswith("/takip_liste"):
            from app.services.watchlist import get_watchlist
            wl = get_watchlist()
            if not wl:
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "Listenizde takip edilen oyuncu yok."})
                return
            msg = "🎯 *TAKİP LİSTENİZ* 🎯\n\n"
            for ea_id, data in wl.items():
                status = "✅ Bildirim Gitti" if data.get('notified') else "⏳ İzleniyor"
                msg += f"• {data['rating']} {data['name']} - Hedef: {data['target_price']:,} 🪙 ({status})\n"
            await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
            return

        if text.startswith("/takip"):
            # Format: /takip 89 mbappe 2500000
            parts = text.replace("/takip", "").strip().split()
            if len(parts) < 3:
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "Kullanım: /takip [reyting] [isim] [hedef fiyat]\nÖrnek: /takip 89 mbappe 2500000"})
                return

            try:
                rating = int(parts[0])
                target_price = int(parts[-1].replace('.', '').replace(',', ''))
                name_query = " ".join(parts[1:-1])
            except:
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "Hatalı format. Lütfen fiyatı ve reytingi rakamla yazın."})
                return

            raw_results = await self.service.search(name_query, limit=5)
            if not raw_results:
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "Oyuncu bulunamadı."})
                return

            results = sorted(raw_results, key=lambda x: abs((x.get("rating") or 0) - rating))
            card_info = results[0]

            from app.services.watchlist import add_to_watchlist
            add_to_watchlist(card_info['ea_id'], card_info['name'], card_info['rating'], target_price)

            await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": f"✅ {card_info['rating']} {card_info['name']} takip listesine eklendi.\n\nFiyatı {target_price:,} 🪙 altına düştüğünde size anında haber vereceğim! 🎯"})
            return

        if text.startswith("/rapor"):
            try:
                from sqlalchemy import text
                with self.service._repo._engine.connect() as conn:
                    # En değerli oyuncular raporu
                    sql = text('''
                        SELECT c.rating, c.name, p.price
                        FROM catalog_card c
                        JOIN price_cache p ON c.ea_id = p.ea_id
                        WHERE p.price > 100000
                        ORDER BY p.price DESC
                        LIMIT 5
                    ''')
                    rows = conn.execute(sql).fetchall()

                msg = "📰 *GÜNLÜK PİYASA RAPORU* 📰\n\n"
                msg += "📈 *Piyasadaki En Değerli Kartlar:*\n"
                for i, r in enumerate(rows, 1):
                    msg += f"{i}. {r.rating} {r.name} - {r.price:,} 🪙\n"
                msg += "\nSistem yeni olduğu için detaylı düşüş/çıkış analizi (trend) verileri toplanıyor, birkaç gün içinde aktif olacak."

                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
            except Exception as e:
                pass
            return

        if text in ["/komut", "/komutlar", "/help"]:
            msg = "🤖 *FC 27 ASİSTAN BOT KOMUTLARI* 🤖\n\n"

            msg += "🔍 *ARAMA & TRANSFER LİSTESİ*\n"
            msg += "• `/fiyat 84 ronaldo` : Tek bir oyuncunun fiyatını söyler.\n"
            msg += "• `/toplu 89 mbappe, 83 casemiro` : Aralarına virgül koyarak yazdığınız oyuncuların tek tek ve toplam maliyetini fiş olarak verir.\n"
            msg += "• 📸 *Fotoğraf Gönder* : Oyundan transfer listesinin veya kadronun fotoğrafını atarsanız, isimleri okuyup toplam değeri hesaplar.\n\n"

            msg += "🧩 *KADRO KURMA*\n"
            msg += "• `/ucuz 84x5` : İstediğiniz reytingdeki en ucuz oyuncuları ve toplam maliyetini bulur (Örn: 5 tane 84'lük).\n\n"

            msg += "🎯 *VIP SNIPE & PİYASA*\n"
            msg += "• `/tcp 100000` : Bütçene uygun, kâr bırakacak 'Over Priced' fırsatlarını (TCP Taktik) listeler.\n"
            msg += "• `/takip 89 mbappe 2500000` : Oyuncuyu hedefe alır, fiyatı 2.5M altına düştüğü an telefonunuza alarm çaldırır!\n"
            msg += "• `/takip_liste` : Hedefe alıp alarm kurduğunuz oyuncuları gösterir.\n"
            msg += "• `/rapor` : Veritabanındaki en değerli/pahalı oyuncuların borsa özetini sunar.\n\n"

            msg += "📊 *SİSTEM*\n"
            msg += "• `/durum` : Arka plandaki Veri Doldurucu (Auto-Feeder) robotunun veritabanına kaç kart depoladığını canlı gösterir.\n"

            await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
            return

        if text and "PS:" in text and "PC:" in text and "\n\n" in text:
            import asyncio
            asyncio.create_task(self._process_bulk(chat_id, text))
            return

        if text.startswith("/sat "):
            try:
                buy_price = int(text.split()[1].replace('.', '').replace(',', ''))

                def round_fifa(val):
                    if val > 100000: return round(val / 1000) * 1000
                    if val > 50000: return round(val / 500) * 500
                    if val > 10000: return round(val / 250) * 250
                    if val > 1000: return round(val / 100) * 100
                    return round(val / 50) * 50

                p1 = round_fifa(buy_price * 1.10)
                p2 = round_fifa(buy_price * 1.12)
                p3 = round_fifa(buy_price * 1.14)
                p4 = round_fifa(buy_price * 1.16)

                msg = f"📈 **YATIRIM SATIŞ PLANI** (Alış: {buy_price:,} 🪙)\n\n"
                msg += f"📦 %20'lik Kısım (+%10) -> **{p1:,}** 🪙 (Net kâr: {int(p1*0.95 - buy_price):,} 🪙)\n"
                msg += f"📦 %20'lik Kısım (+%12) -> **{p2:,}** 🪙 (Net kâr: {int(p2*0.95 - buy_price):,} 🪙)\n"
                msg += f"📦 %20'lik Kısım (+%14) -> **{p3:,}** 🪙 (Net kâr: {int(p3*0.95 - buy_price):,} 🪙)\n"
                msg += f"📦 %20'lik Kısım (+%16) -> **{p4:,}** 🪙 (Net kâr: {int(p4*0.95 - buy_price):,} 🪙)\n"
                msg += "\n⚠️ *Fiyatlara %5 EA Tax dahildir. Erkenden listede olduğundan emin ol!*"

                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
                return
            except:
                pass

        if " / " in text and len(text.split(" / ")) > 3:
            import asyncio
            asyncio.create_task(self._process_slash_list(chat_id, text))
            return

        if text == "/durum":
            try:
                from sqlalchemy import text
                with self.service._repo._engine.connect() as conn:
                    total_cards = conn.execute(text("SELECT COUNT(*) FROM catalog_card")).fetchone()[0]
                    fetched_details = conn.execute(text("SELECT COUNT(*) FROM catalog_card WHERE details_fetched = 1")).fetchone()[0]
                    known_prices = conn.execute(text("SELECT COUNT(*) FROM price_cache")).fetchone()[0]

                    msg = "📊 *VERİTABANI DURUMU (AUTO-FEEDER)* 📊\n\n"
                    msg += f"📦 Toplam Kart (Sistemdeki EA ID): {total_cards:,}\n"
                    msg += f"🔍 Detayı Çekilmiş Oyuncu: {fetched_details:,}\n"
                    msg += f"💰 Fiyatı Bilinen Oyuncu: {known_prices:,}\n\n"
                    msg += "⏳ *Not:* Auto-Feeder arka planda her 20 saniyede bir yeni oyuncu fiyatı çekmeye devam ediyor. Hızlandırırsak FUTBIN sistemleri IP adresinizi banlayacağı için (Bot Koruması) bu hız en güvenli sınırdır. Acil lazım olanları direkt bota yazarak kendin hızlıca çekebilirsin."

                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
            except Exception as e:
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": f"Hata: {str(e)}"})
            return

        if text.startswith("/tcp"):
            parts = text.strip().split()
            if len(parts) < 2:
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "Lütfen bütçenizi girin. Örnek: /tcp 50000"})
                return
            try:
                budget = int(parts[1])
                from .tcp_analyzer import get_tcp_recommendations
                recs = get_tcp_recommendations(self.service._repo._engine, budget, platform="pc")
                if not recs:
                    msg = "❌ Bu bütçeye uygun TCP kâr fırsatı şu an bulunamadı."
                else:
                    msg = "📈 *TCP (Fırsat Kartları)* 📈\n_Tembel alıcılara kârla satmalık listemiz:_\n\n"
                    for r in recs:
                        msg += f"🔥 *{r['name']}* ({r['rating']} {r['position']})\n"
                        msg += f"🛒 *Max Alış Fiyatı:* {r['current_price']:,} jeton ({r['qty']})\n"
                        msg += f"🎯 *Hedef Satış (Buy Now):* {r['target_sell']:,} jeton\n"
                        msg += f"⚠️ *Açılış (Min Bid):* En az {r['min_bid']:,} jeton\n"
                        msg += f"💰 *Net Kâr (EA Kesintisi Sonrası):* +{r['profit']:,}\n"
                        msg += f"📉 *Zararına Çıkış (Break-even):* {r['break_even']:,} jeton (Satılmazsa)\n"
                        msg += f"🧪 *Önerilen Kimya:* {r['chem_style']}\n\n"
                    msg += "🔄 *Taktik:* Satılmazsa listelemeyi yenile. Yine satılmazsa %2-5 düşür. Yine satılmazsa zararına çıkış fiyatından sat.\n"
                    msg += "💡 *İpucu:* Yeni içerikten 55 dk önce alırsan çok daha rahat satarsın."

                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
            except ValueError:
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "Hatalı bütçe formatı. Lütfen sayı girin (Örn: 50000)."})
            except Exception as e:
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": f"Hata: {str(e)}"})
            return

        if text.startswith("/ucuz"):
            query = text.replace("/ucuz", "").strip()
            import re

            match = re.search(r'\b(\d{2})(?:\s*[xX]\s*(\d{1,2}))?\b', query)
            if not match:
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "Lütfen reyting veya reyting x sayı yazın. Örnek: /ucuz 84 veya /ucuz 84x5"})
                return

            target_rating = int(match.group(1))
            limit = int(match.group(2)) if match.group(2) else 10
            if limit > 50: limit = 50

            try:
                from sqlalchemy import text
                with self.service._repo._engine.connect() as conn:
                    sql = text('''
                        SELECT c.name, p.price
                        FROM catalog_card c
                        JOIN price_cache p ON c.ea_id = p.ea_id
                        WHERE c.rating = :r AND p.price > 0
                        ORDER BY p.price ASC
                        LIMIT :limit
                    ''')
                    rows = conn.execute(sql, {"r": target_rating, "limit": limit}).fetchall()

                if not rows:
                    await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": f"Veritabanında {target_rating} reytingli fiyatı bilinen oyuncu bulunamadı."})
                    return

                msg = f"📉 *EN UCUZ {target_rating} REYTİNG OYUNCULAR (Top {len(rows)})* 📉\n\n"
                total_cost = 0
                for i, r in enumerate(rows, 1):
                    msg += f"{i}. {r.name}: {r.price:,} 🪙\n"
                    total_cost += r.price

                msg += f"\n💰 *TOPLAM MALİYET:* {total_cost:,} 🪙"

                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
            except Exception as e:
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": f"Hata: {str(e)}"})
            return

        if text.startswith("/fiyat"):
            import re
            query = text.replace("/fiyat", "").strip()
            if not query:
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": "Lütfen oyuncu adı ve reyting yazın. Örnek: /fiyat 84 ronaldo"})
                return

            # Reyting analizi
            rating_match = re.search(r'\b(\d{2})\b', query)
            expected_rating = int(rating_match.group(1)) if rating_match else None
            if expected_rating:
                query = re.sub(r'\b\d{2}\b', '', query).strip()

            await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": f"Aranıyor: {query} {'(Reyting: '+str(expected_rating)+')' if expected_rating else ''} ..."})
            try:
                # 15 sonuç al, reytinge göre filtrele (varsa)
                raw_results = await self.service.search(query, limit=15)

                # Her zaman en yüksek reytingliyi en üste al
                raw_results = sorted(raw_results, key=lambda x: -(x.get("rating") or 0))

                if expected_rating and raw_results:
                    # Sort results by closest rating to expected_rating
                    results = sorted(raw_results, key=lambda x: abs((x.get("rating") or 0) - expected_rating))
                else:
                    results = raw_results

                if not results:
                    await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": f"Oyuncu bulunamadı: {query}"})
                    return

                card_info = results[0]
                ea_id = card_info["ea_id"]
                card = self.service._repo.card(ea_id)
                if card:
                    quote, failures = await self.service._prices.get(card, force_refresh=True)
                    if quote and quote.price:
                        msg = f"{card.rating} {card.name}\nGüncel Fiyat (PC): {quote.price:,} coins"
                    else:
                        msg = f"{card.rating} {card.name} için fiyat alınamadı."
                    await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": msg})
            except Exception as e:
                await self.client.post(f"{self.base_url}/sendMessage", json={"chat_id": chat_id, "text": f"Hata oluştu: {e}"})
