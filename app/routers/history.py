"""Price history for one card.

The series is built only from prices this app actually observed -- there is no
background polling and no third-party history is mixed in, so every point is a
real PC-market reading taken while you were using the tool.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from ..core.config import settings
from ..core.state import state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cards", tags=["history"])

RANGES: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


@router.get("/{ea_id}/history")
async def card_history(
    ea_id: int,
    range: str = Query(default="24h", pattern="^(1h|24h|7d)$"),
) -> dict:
    repo = state.require_repo()

    card = repo.card(ea_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Kart katalogda yok: {ea_id}")

    window = RANGES[range]
    since = datetime.now(timezone.utc) - window
    points = repo.price_history(ea_id, since)
    tax = settings.ea_tax_rate

    return {
        "ea_id": ea_id,
        "range": range,
        "tax_rate": tax,
        "points": [
            {
                "t": p.recorded_at.isoformat(),
                "bin": p.price,
                "net": int(round(p.price * (1 - tax))),
                "platform": p.platform,
                "source": p.source,
            }
            for p in points
        ],
        # Totals let the UI say "0 in this window, 12 overall" instead of
        # looking broken on a fresh install.
        "in_range": len(points),
        "total_recorded": repo.price_point_count(ea_id),
    }
