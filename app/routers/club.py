from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter(prefix="/api/club", tags=["club"])

# In-memory club storage for speed and simplicity
# instance_id -> {definition_id, untradeable}. Legacy entries may be bools.
my_club_inventory = {}

class ClubItem(BaseModel):
    ea_id: int
    instance_id: str | None = None
    item_score: int = 0
    untradeable: bool

class SyncClubRequest(BaseModel):
    items: List[ClubItem]

@router.post("/sync")
async def sync_club(req: SyncClubRequest):
    added = 0
    for item in req.items:
        key = item.instance_id or str(item.ea_id)
        if key not in my_club_inventory:
            added += 1
        my_club_inventory[key] = {"definition_id": str(item.ea_id), "untradeable": item.untradeable,
                                  "item_score": item.item_score}

    return {"status": "ok", "total_in_club": len(my_club_inventory), "newly_added": added}

@router.get("/info")
async def get_club_info():
    return {"total": len(my_club_inventory)}
