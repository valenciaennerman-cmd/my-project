from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import datetime

from ..core.db import get_session
from ..models.tables import Investment, CatalogCard, PriceCache, utcnow
from pydantic import BaseModel

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

class InvestmentCreate(BaseModel):
    ea_id: int
    buy_price: int
    quantity: int = 1
    target_price: int | None = None

class InvestmentResponse(BaseModel):
    id: int
    ea_id: int
    name: str
    rating: int
    buy_price: int
    current_price: int | None
    quantity: int
    profit: int | None
    status: str
    bought_at: datetime

@router.post("/add")
async def add_investment(inv: InvestmentCreate, db: Session = Depends(get_session)):
    card = db.exec(select(CatalogCard).where(CatalogCard.ea_id == inv.ea_id)).first()
    if not card:
        raise HTTPException(status_code=404, detail="Kart bulunamadı")

    new_inv = Investment(
        ea_id=inv.ea_id,
        buy_price=inv.buy_price,
        quantity=inv.quantity,
        target_price=inv.target_price
    )
    db.add(new_inv)
    db.commit()
    db.refresh(new_inv)
    return {"status": "success", "investment_id": new_inv.id}

@router.get("/list", response_model=List[InvestmentResponse])
async def list_investments(db: Session = Depends(get_session)):
    investments = db.exec(select(Investment).where(Investment.status == "active").order_by(Investment.bought_at.desc())).all()

    res = []
    for inv in investments:
        card = db.exec(select(CatalogCard).where(CatalogCard.ea_id == inv.ea_id)).first()
        pc = db.exec(select(PriceCache).where(PriceCache.ea_id == inv.ea_id, PriceCache.platform == "pc")).first()

        current_price = pc.price if pc else None

        profit = None
        if current_price is not None:
            # %5 EA Tax
            net_sell = current_price * 0.95
            profit = int((net_sell - inv.buy_price) * inv.quantity)

        res.append(InvestmentResponse(
            id=inv.id,
            ea_id=inv.ea_id,
            name=card.name if card else "Bilinmeyen",
            rating=card.rating if card else 0,
            buy_price=inv.buy_price,
            current_price=current_price,
            quantity=inv.quantity,
            profit=profit,
            status=inv.status,
            bought_at=inv.bought_at
        ))
    return res

@router.post("/sell/{inv_id}")
async def sell_investment(inv_id: int, sell_price: int, db: Session = Depends(get_session)):
    inv = db.exec(select(Investment).where(Investment.id == inv_id)).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Yatırım bulunamadı")

    inv.status = "sold"
    inv.sell_price = sell_price
    inv.sold_at = utcnow()

    db.add(inv)
    db.commit()
    return {"status": "success", "profit": int((sell_price * 0.95 - inv.buy_price) * inv.quantity)}
