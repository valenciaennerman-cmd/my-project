import asyncio
import logging
from sqlalchemy import text
from app.core.state import state

logger = logging.getLogger("fc27")

class AutoFeeder:
    def __init__(self):
        self.running = False
        self.task = None
        self.loop_count = 0

    async def start(self):
        self.running = True
        self.task = asyncio.create_task(self._loop())
        logger.info("Auto-Feeder (SBC Veri Doldurucu) basladi. Arka planda sessizce fiyat cekecek.")

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()

    async def _loop(self):
        from app.services.watchlist import get_watchlist, mark_notified
        from app.core.config import settings
        import httpx

        while self.running:
            try:
                self.loop_count += 1
                await asyncio.sleep(2)  # Normal detay cekmek icin kisa bekleme
                service = state.require_service()
                db = service._repo

                # --- VIP WATCHLIST KONTROLU (Sadece 100 dongude bir) ---
                if self.loop_count % 100 == 1:
                    wl = get_watchlist()
                    if wl:
                        for ea_id_str, data in wl.items():
                            if not data.get("notified"):
                                card = db.card(int(ea_id_str))
                                if card:
                                    quote, _ = await service._prices.get(card)
                                    if quote and quote.price > 0 and quote.price <= data["target_price"]:
                                        mark_notified(int(ea_id_str))
                                        msg = f"🚨 **VIP SNIPE ALARMI!** 🚨\n\n💥 {data['rating']} {data['name']} hedef fiyatın olan {data['target_price']:,} 🪙 altına düştü!\n💰 Güncel Fiyat: {quote.price:,} 🪙\n\nHemen oyuna girip satın al!"
                                        try:
                                            async with httpx.AsyncClient() as client:
                                                await client.post(
                                                    f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
                                                    json={"chat_id": settings.telegram_chat_id, "text": msg, "parse_mode": "Markdown"}
                                                )
                                        except Exception as e:
                                            logger.error(f"Telegram alert hatası: {e}")
                                    await asyncio.sleep(8)
                # -----------------------------

                with db._engine.connect() as conn:
                    # Oncelik: Hic detayi alinmamis oyunculardan rastgele sec (Hizlandirmak icin LIMIT 3 yapalim ve pes pese tarayalim)
                    query = text("""
                        SELECT base_player_ea_id
                        FROM catalog_card
                        WHERE details_fetched = 0 OR details_fetched IS NULL
                        ORDER BY RANDOM()
                        LIMIT 3
                    """)
                    rows = conn.execute(query).fetchall()

                if rows:
                    for row in rows:
                        base_id = row[0]
                        try:
                            # Detaylari cek (Rating, Kulup vs.)
                            cards = await service.ensure_player_cards(base_id)
                        except Exception as fetch_exc:
                            logger.warning(f"Auto-Feeder gecici hata: {fetch_exc}")
                            # 404 veya baska kalici hata durumunda sonsuz donguye girmemek icin isaretle
                            with db._engine.connect() as conn:
                                conn.execute(text("UPDATE catalog_card SET details_fetched = 1 WHERE base_player_ea_id = :base_id"), {"base_id": base_id})
                                conn.commit()
                            continue

                        # Reytingi 80 ile 89 arasindaki kartlarin fiyatini cek
                        for card in cards:
                            if card.rating and 80 <= card.rating <= 89:
                                await asyncio.sleep(10) # 15'ten 10'a dusurdum, biraz daha hizli
                                await service._prices.get(card)

                        await asyncio.sleep(1) # Diger karta gecmeden 1 saniye bekle

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Auto-Feeder gecici hata: {e}")
                await asyncio.sleep(30)

feeder = AutoFeeder()
