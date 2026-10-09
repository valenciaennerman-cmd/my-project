import json
import os
from pathlib import Path

WATCHLIST_FILE = Path("data/watchlist.json")

def load_watchlist():
    if not WATCHLIST_FILE.exists():
        return {}
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_watchlist(data):
    WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_to_watchlist(ea_id: int, name: str, rating: int, target_price: int):
    data = load_watchlist()
    data[str(ea_id)] = {
        "name": name,
        "rating": rating,
        "target_price": target_price,
        "notified": False
    }
    save_watchlist(data)

def remove_from_watchlist(ea_id: int):
    data = load_watchlist()
    if str(ea_id) in data:
        del data[str(ea_id)]
        save_watchlist(data)
        return True
    return False

def get_watchlist():
    return load_watchlist()

def mark_notified(ea_id: int):
    data = load_watchlist()
    if str(ea_id) in data:
        data[str(ea_id)]["notified"] = True
        save_watchlist(data)
