import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

def get_tcp_recommendations(engine, budget: int, platform: str = "pc", limit: int = 5):
    """
    Finds TCP (Trading Card Prediction) opportunities based on historical average.
    Returns a list of dictionaries with card info, buy price, expected sell price, and chem style.
    """
    with engine.connect() as conn:
        query = text("""
            WITH avg_prices AS (
                SELECT ea_id, AVG(price) as avg_price, COUNT(id) as dp_count
                FROM price_point
                WHERE platform = :platform
                  AND recorded_at >= datetime('now', '-3 days')
                  AND price > 0
                GROUP BY ea_id
                HAVING dp_count >= 2
            )
            SELECT c.ea_id, c.name, c.rating, c.position, c.version_label, c.image_url,
                   p.price as current_price, a.avg_price
            FROM catalog_card c
            JOIN price_cache p ON c.ea_id = p.ea_id
            JOIN avg_prices a ON c.ea_id = a.ea_id
            WHERE p.platform = :platform
              AND p.price > 0
              AND p.price <= :budget
              AND a.avg_price > p.price * 1.15
            ORDER BY (a.avg_price - p.price) DESC
            LIMIT :limit
        """)

        rows = conn.execute(query, {"platform": platform, "budget": budget, "limit": limit}).fetchall()

    results = []
    for r in rows:
        pos = (r.position or "").upper()
        if pos in ['ST', 'CF', 'RW', 'LW', 'RM', 'LM']:
            chem = "Hunter / Hawk"
        elif pos in ['CM', 'CAM', 'CDM']:
            chem = "Shadow / Engine"
        elif pos in ['CB', 'RB', 'LB', 'RWB', 'LWB']:
            chem = "Shadow / Anchor"
        elif pos in ['GK']:
            chem = "Glove / Basic"
        else:
            chem = "Basic"

        qty = "2-3 Adet" if r.current_price < 10000 else "1 Adet"
        target_sell = int(r.avg_price)
        min_bid = int(target_sell * 0.95) # Keep start price very high to avoid losses
        if min_bid < r.current_price:
            min_bid = r.current_price + 250

        break_even = int(r.current_price / 0.95) # Price to sell just to cover EA 5% Tax

        results.append({
            "name": r.name,
            "rating": r.rating,
            "version": r.version_label or "Altin",
            "position": r.position,
            "image_url": r.image_url,
            "current_price": r.current_price,
            "target_sell": target_sell,
            "min_bid": min_bid,
            "break_even": break_even,
            "qty": qty,
            "profit": int((target_sell * 0.95) - r.current_price), # Net profit after EA tax
            "chem_style": chem
        })

    # If no data with 3-day history, fallback
    if not results:
        with engine.connect() as conn:
            query = text("""
                SELECT c.ea_id, c.name, c.rating, c.position, c.version_label, c.image_url, p.price as current_price
                FROM catalog_card c
                JOIN price_cache p ON c.ea_id = p.ea_id
                WHERE p.platform = :platform
                  AND p.price > 0
                  AND p.price <= :budget
                  AND c.rating >= 84
                ORDER BY p.price ASC
                LIMIT :limit
            """)
            rows = conn.execute(query, {"platform": platform, "budget": budget, "limit": limit}).fetchall()

            for r in rows:
                pos = (r.position or "").upper()
                chem = "Hunter" if pos in ['ST','CF','RW','LW','RM','LM'] else "Shadow"

                qty = "2-3 Adet" if r.current_price < 10000 else "1 Adet"
                target_sell = int(r.current_price * 1.2)
                min_bid = int(target_sell * 0.95)
                break_even = int(r.current_price / 0.95)

                results.append({
                    "name": r.name,
                    "rating": r.rating,
                    "version": r.version_label or "Altin",
                    "position": r.position,
                    "image_url": r.image_url,
                    "current_price": r.current_price,
                    "target_sell": target_sell,
                    "min_bid": min_bid,
                    "break_even": break_even,
                    "qty": qty,
                    "profit": int((target_sell * 0.95) - r.current_price),
                    "chem_style": chem
                })

    return results
