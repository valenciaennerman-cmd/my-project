from fastapi import APIRouter, Request
from pydantic import BaseModel
import logging

from app.core.state import state
from app.services.tcp_analyzer import get_tcp_recommendations

router = APIRouter(prefix="/api/tcp", tags=["tcp"])
logger = logging.getLogger(__name__)

class TCPRequest(BaseModel):
    budget: int
    platform: str = "pc"
    risk: str = "safe" # future proofing

@router.post("/recommendations")
async def get_recommendations(req: TCPRequest):
    try:
        engine = state.require_service()._repo._engine
        # we can fetch more (e.g. limit=20) for the UI
        recs = get_tcp_recommendations(engine, req.budget, platform=req.platform.lower(), limit=20)

        # calculate stats for the top bar
        spend = sum(r["current_price"] * (2 if "2-3" in r["qty"] else 1) for r in recs)
        expected_profit = sum(r["profit"] * (2 if "2-3" in r["qty"] else 1) for r in recs)
        avg_margin = 0
        if spend > 0:
            avg_margin = (expected_profit / spend) * 100

        return {
            "status": "ok",
            "stats": {
                "listings": len(recs),
                "spend": spend,
                "expected_profit": expected_profit,
                "avg_margin": round(avg_margin, 1)
            },
            "recommendations": recs
        }
    except Exception as e:
        logger.exception("TCP API Error")
        return {"status": "error", "message": str(e)}
