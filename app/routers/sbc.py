import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from typing import List, Optional, Literal

from ..core.db import get_session
from ..models.tables import CatalogCard, PriceCache
from .club import my_club_inventory

from ..services.sbc.models import CanonicalPlayer, NormalizedChallenge, Requirement as SBCRequirementModel
from ..services.sbc.multi_completion import MultiCompletionEngine
from ..services.sbc.verifier import IndependentVerifier
from ..services.sbc.swap import SwapEngine
from ..services.sbc.chemistry import calculate_chemistry
from ..services.sbc.solver_normal import CPNormalSolver
from ..services.sbc.solver_streamlined import CPStreamlinedSolver
from ..services.sbc.models import SolverStatus

router = APIRouter(prefix="/api/sbc", tags=["sbc"])

class RequirementReq(BaseModel):
    req_type: str
    val: int
    scope: str = "MIN"

class SolveRequest(BaseModel):
    mode: Literal["NORMAL", "STREAMLINED"] = "NORMAL"
    target_score: int = 0
    target_rating: int = Field(alias="min_rating", default=84)
    min_chem: int = 0
    min_totw: int = 0
    protect_expensive: bool = True
    prefer_untradeable: bool = True
    completion_count: int = Field(default=1, ge=1, le=5)
    locked_players: List[dict] = Field(default_factory=list)

class SwapRequest(BaseModel):
    current_squad: List[dict]
    original_instance_id: Optional[str] = None
    original_definition_id: Optional[str] = None
    target_rating: int = Field(alias="min_rating", default=84)
    min_chem: int = 0
    min_totw: int = 0
    protect_expensive: bool = True
    prefer_untradeable: bool = True
    mode: Literal["NORMAL", "STREAMLINED"] = "NORMAL"
    target_score: int = 0

class VerifyRequest(BaseModel):
    squad: List[dict]
    target_rating: int = Field(alias="min_rating", default=84)
    min_chem: int = 0
    min_totw: int = 0
    mode: Literal["NORMAL", "STREAMLINED"] = "NORMAL"
    target_score: int = 0

def build_pool(db, req_target_rating: int, protect_expensive: bool, prefer_untradeable: bool = True) -> List[CanonicalPlayer]:
    available_players = []

    if my_club_inventory:
        owned = [(str(key), value.get("definition_id", str(key)) if isinstance(value, dict) else str(key),
                  value.get("untradeable", False) if isinstance(value, dict) else bool(value),
                  value.get("item_score", 0) if isinstance(value, dict) else 0)
                 for key, value in my_club_inventory.items()]
        club_ea_ids = [int(definition_id) for _, definition_id, _, _ in owned if definition_id.isdigit()]
        club_cards = db.exec(select(CatalogCard).where(CatalogCard.ea_id.in_(club_ea_ids))).all()
        cards_by_id = {str(card.ea_id): card for card in club_cards}
        for instance_id, definition_id, is_untradeable, item_score in owned:
            card = cards_by_id.get(definition_id)
            if card is None:
                continue
            price = 0
            pc = db.exec(select(PriceCache).where(PriceCache.ea_id == card.ea_id, PriceCache.platform == "pc")).first()
            if pc and pc.price:
                price = pc.price

            is_totw = bool(card.rarity_name and "Team of the Week" in card.rarity_name)

            excluded = False
            if protect_expensive and price > 50000:
                excluded = True

            p = CanonicalPlayer(
                definition_id=str(card.ea_id),
                instance_id=instance_id,
                item_score=item_score,
                name=card.name,
                rating=card.rating or 0,
                is_rare=False,
                is_special=is_totw,
                market_price=price,
                tradeable=not is_untradeable,
                excluded=excluded,
                prefer_untradeable=prefer_untradeable,
                is_concept=False,
                league_id=hash(card.league_name) if getattr(card, "league_name", None) else None,
                nation_id=hash(card.nation_name) if getattr(card, "nation_name", None) else None,
                club_id=hash(card.club_name) if getattr(card, "club_name", None) else None
            )
            available_players.append(p)

    for rtg in range(max(75, req_target_rating - 5), req_target_rating + 4):
        stmt = (
            select(CatalogCard, PriceCache.price)
            .join(PriceCache, CatalogCard.ea_id == PriceCache.ea_id)
            .where(CatalogCard.rating == rtg, PriceCache.platform == "pc", PriceCache.price > 0)
            .order_by(PriceCache.price.asc())
            .limit(2)
        )
        cheap_cards = db.exec(stmt).all()
        for c, price in cheap_cards:
            if str(c.ea_id) not in {p.definition_id for p in available_players}:
                is_totw = bool(c.rarity_name and "Team of the Week" in c.rarity_name)
                p = CanonicalPlayer(
                    definition_id=str(c.ea_id),
                    instance_id=f"concept:{c.ea_id}",
                    name=c.name + " (Konsept)",
                    rating=c.rating or 0,
                    is_special=is_totw,
                    market_price=price,
                    tradeable=True,
                    prefer_untradeable=prefer_untradeable,
                    is_concept=True,
                    league_id=hash(c.league_name) if getattr(c, "league_name", None) else None,
                    nation_id=hash(c.nation_name) if getattr(c, "nation_name", None) else None,
                    club_id=hash(c.club_name) if getattr(c, "club_name", None) else None
                )
                available_players.append(p)

    return available_players

def build_challenge(target_rating: int, min_chem: int, min_totw: int, mode: str = "NORMAL", target_score: int = 0) -> NormalizedChallenge:
    reqs = []
    if mode == "NORMAL" and target_rating > 0:
        reqs.append(SBCRequirementModel(req_type="TEAM_RATING", val=target_rating, scope="MIN"))
    if min_chem > 0:
        reqs.append(SBCRequirementModel(req_type="MIN_CHEM", val=min_chem, scope="MIN"))
    if min_totw > 0:
        reqs.append(SBCRequirementModel(req_type="MIN_TOTW", val=min_totw, scope="MIN"))

    return NormalizedChallenge(
        challenge_id="custom_ui",
        name="UI Challenge",
        type=mode,
        required_player_count=11,
        requirements=reqs,
        score_requirement=target_score if mode == "STREAMLINED" else None,
    )

def parse_squad(squad_dict: List[dict]) -> List[CanonicalPlayer]:
    res = []
    for d in squad_dict:
        # handle legacy dict format or just extract necessary fields
        p = CanonicalPlayer(
            definition_id=str(d.get("definition_id") or d.get("ea_id")),
            instance_id=str(d["instance_id"]) if d.get("instance_id") is not None else None,
            name=d.get("name", "Unknown"),
            rating=d.get("rating", 0),
            market_price=d.get("market_price") or d.get("price") or 0,
            locked=d.get("locked", False),
            is_concept=d.get("is_concept", False),
            league_id=d.get("league_id"),
            nation_id=d.get("nation_id"),
            club_id=d.get("club_id"),
            is_special=d.get("is_special") or d.get("is_totw") or False
        )
        res.append(p)
    return res

@router.post("/solve")
async def solve_sbc(req: SolveRequest, db: Session = Depends(get_session)):
    if req.mode == "STREAMLINED" and req.target_score <= 0:
        raise HTTPException(status_code=422, detail="Streamlined target_score must be positive")
    start_time = time.time()
    pool = build_pool(db, req.target_rating, req.protect_expensive, req.prefer_untradeable)

    locked_ids = set()
    for locked in req.locked_players:
        if locked.get("instance_id") is not None:
            locked_ids.add(str(locked["instance_id"]))
        else:
            matches = [p.instance_id for p in pool if p.definition_id == str(locked.get("definition_id") or locked.get("ea_id"))]
            if len(matches) != 1:
                raise HTTPException(status_code=409, detail="Lock requires an unambiguous instance_id")
            locked_ids.add(matches[0])
    pool_by_id = {p.instance_id: p for p in pool}
    if not locked_ids.issubset(pool_by_id):
        raise HTTPException(status_code=409, detail="Locked instance is no longer in inventory")
    for instance_id in locked_ids:
        pool_by_id[instance_id].locked = True
        pool_by_id[instance_id].excluded = False

    if not pool:
        raise HTTPException(status_code=400, detail="Kulüp boş ve konsept havuzu yüklenemedi.")

    challenge = build_challenge(req.target_rating, req.min_chem, req.min_totw, req.mode, req.target_score)

    if req.completion_count == 1:
        solver_result = (CPStreamlinedSolver(pool).solve_with_status(challenge) if req.mode == "STREAMLINED"
                         else CPNormalSolver(pool).solve_with_status(challenge))
        completions = [solver_result.squad] if solver_result.success else []
    else:
        solver_result = MultiCompletionEngine(pool).solve_with_status(challenge, req.completion_count, mode="EXACT")
        completions = solver_result.metadata.get("completions", [])
    if not completions:
        return {"status": "no_result", "solver_status": solver_result.status.value,
                "metadata": {k: v for k, v in solver_result.metadata.items() if k != "completions"}, "squad": []}

    squad = completions[0] # Just returning the first completion for UI simplicity for now

    calc_time_ms = int((time.time() - start_time) * 1000)

    # Need to return dicts with image_url for UI
    squad_dicts = []
    for p in squad:
        d = p.model_dump()
        # Find image_url
        c = db.exec(select(CatalogCard).where(CatalogCard.ea_id == int(p.definition_id))).first()
        d["image_url"] = c.image_url if c else "https://fifa21.content.easports.com/fifa/fltOnlineAssets/0536A1DE-E2F5-467E-8D29-593B6201B7FA/2021/fut/items/images/players/html5/240x240/p237067.png"
        d["ea_id"] = p.definition_id
        d["price"] = p.market_price
        squad_dicts.append(d)

    ratings = [p.rating for p in squad]
    base_avg = sum(ratings) / len(ratings) if ratings else 0
    total_diff = sum((r - base_avg) for r in ratings if r > base_avg)
    verification = (IndependentVerifier.verify_streamlined_squad(squad, challenge, req.target_score, inventory=pool)
                    if req.mode == "STREAMLINED" else IndependentVerifier.verify_normal_squad(squad, challenge, inventory=pool))
    if not verification["valid"]:
        return {"status": "no_result", "solver_status": SolverStatus.ERROR.value,
                "metadata": {"diagnostic": "Solver output failed independent verification", "errors": verification["errors"]},
                "squad": []}
    actual_rating = verification.get("team_rating")

    return {
        "status": "success" if solver_result.success else "partial",
        "solver_status": solver_result.status.value,
        "completion_count": len(completions),
        "verification": verification,
        "total_cost": sum(p.effective_cost for p in squad),
        "calc_time_ms": calc_time_ms,
        "actual_rating": actual_rating,
        "total_score": verification.get("total_score"),
        "target_score": req.target_score if req.mode == "STREAMLINED" else None,
        "actual_chem": calculate_chemistry(squad),
        "squad": squad_dicts
    }

@router.post("/swap")
async def swap_player(req: SwapRequest, db: Session = Depends(get_session)):
    if req.mode == "STREAMLINED" and req.target_score <= 0:
        raise HTTPException(status_code=422, detail="Streamlined target_score must be positive")
    pool = build_pool(db, req.target_rating, req.protect_expensive, req.prefer_untradeable)
    by_instance = {p.instance_id: p for p in pool}
    ids = [str(p.get("instance_id")) for p in req.current_squad]
    if len(set(ids)) != len(ids) or any(i not in by_instance for i in ids):
        raise HTTPException(status_code=409, detail="Squad contains duplicate or stale instances")
    current_squad = [by_instance[i].model_copy(update={"locked": bool(req.current_squad[n].get("locked"))}) for n, i in enumerate(ids)]

    if req.original_instance_id is not None:
        original = next((p for p in current_squad if p.instance_id == req.original_instance_id), None)
    else:
        matches = [p for p in current_squad if p.definition_id == req.original_definition_id]
        original = matches[0] if len(matches) == 1 else None
    if not original:
        raise HTTPException(status_code=400, detail="Original player not found in squad")

    challenge = build_challenge(req.target_rating, req.min_chem, req.min_totw, req.mode, req.target_score)

    candidates = [p for p in pool if p.rating == original.rating and p.instance_id not in ids and not p.excluded]

    # Just try the first 5 candidates for demonstration
    results = []
    for cand in candidates[:5]:
        res_squad = SwapEngine.attempt_swap(current_squad, original, cand, challenge, pool)
        verified = (IndependentVerifier.verify_streamlined_squad(res_squad, challenge, req.target_score, inventory=pool)
                    if res_squad and req.mode == "STREAMLINED" else
                    IndependentVerifier.verify_normal_squad(res_squad, challenge, inventory=pool) if res_squad else None)
        if res_squad and verified["valid"]:
            results.append({
                "candidate": cand.model_dump(),
                "requires_repair": any(p.instance_id not in ids and p.instance_id != cand.instance_id for p in res_squad),
                "repaired_squad": [p.model_dump() for p in res_squad]
            })

    return {"status": "success", "results": results,
            "solver_status": (SolverStatus.FEASIBLE.value if results else
                              SolverStatus.INFEASIBLE.value if not candidates else
                              SolverStatus.SEARCH_LIMIT_REACHED.value),
            "search_truncated": len(candidates) > 5}

@router.post("/verify")
async def verify_squad(req: VerifyRequest, db: Session = Depends(get_session)):
    if req.mode == "STREAMLINED" and req.target_score <= 0:
        raise HTTPException(status_code=422, detail="Streamlined target_score must be positive")
    pool = build_pool(db, req.target_rating, False)
    by_instance = {p.instance_id: p for p in pool}
    ids = [str(p.get("instance_id")) for p in req.squad]
    squad = [by_instance[i] for i in ids if i in by_instance]
    challenge = build_challenge(req.target_rating, req.min_chem, req.min_totw, req.mode, req.target_score)

    ver = (IndependentVerifier.verify_streamlined_squad(squad, challenge, req.target_score, inventory=pool)
           if req.mode == "STREAMLINED" else IndependentVerifier.verify_normal_squad(squad, challenge, inventory=pool))
    if len(squad) != len(ids):
        ver["valid"] = False
        ver["errors"].append("Squad contains stale instances")
    if len(set(ids)) != len(ids):
        ver["valid"] = False
        ver["errors"].append("Duplicate instances found in solution.")
    return {"status": "success", "verification": ver}

@router.get("/gems")
async def get_sbc_gems(db: Session = Depends(get_session)):
    fodder_prices = {}
    for rtg in range(80, 92):
        stmt = (
            select(PriceCache.price)
            .join(CatalogCard, CatalogCard.ea_id == PriceCache.ea_id)
            .where(CatalogCard.rating == rtg, PriceCache.platform == "pc", PriceCache.price > 0)
            .order_by(PriceCache.price.asc())
            .limit(5)
        )
        prices = db.exec(stmt).all()
        if prices:
            fodder_prices[rtg] = sum(prices) / len(prices)

    stmt = (
        select(CatalogCard, PriceCache.price)
        .join(PriceCache, CatalogCard.ea_id == PriceCache.ea_id)
        .where(CatalogCard.rating >= 80, PriceCache.platform == "pc", PriceCache.price > 0)
    )
    all_cards = db.exec(stmt).all()

    gems = []
    for c, price in all_cards:
        rating = c.rating or 80
        baseline = fodder_prices.get(rating, 0)
        if baseline > 0 and price > 0:
            score = round(baseline / price, 2)
            if score >= 1.0:
                gems.append({
                    "ea_id": c.ea_id,
                    "name": c.name,
                    "rating": rating,
                    "position": c.position,
                    "price": price,
                    "baseline": round(baseline),
                    "score": score,
                    "image_url": c.image_url
                })

    gems.sort(key=lambda x: (-x["score"], -x["rating"]))

    return {
        "status": "success",
        "fodder_prices": fodder_prices,
        "gems": gems[:100]
    }
