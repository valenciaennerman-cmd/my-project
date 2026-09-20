"""Catalog search, pasted card links, and the sitemap sync."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..core.state import state
from ..services.catalog.futgg import CatalogError
from ..services.matching.links import LinkError, futgg_card_url, parse_card_link

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["catalog"])

FUTBIN_HELP = (
    "FUTBIN bot korumasi yuzunden okunamiyor (robots.txt bile 403 donuyor). "
    "FUT.GG kart linki yapistir ya da arama kutusunu kullan."
)
FUTWIZ_HELP = (
    "FUTWIZ linki kendi ic numarasini tasiyor, EA kart kimligini vermiyor. "
    "FUT.GG kart linki yapistir ya da arama kutusunu kullan."
)


class LinkBody(BaseModel):
    url: str
    scan_id: int | None = None


@router.get("/search")
async def search(q: str = Query(min_length=2)) -> dict:
    return {"results": await state.require_service().search(q)}


@router.post("/link")
async def add_link(body: LinkBody) -> dict:
    service = state.require_service()
    try:
        parsed = parse_card_link(body.url)
    except LinkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if parsed.kind == "futbin":
        raise HTTPException(status_code=400, detail=FUTBIN_HELP)
    if parsed.kind == "futwiz":
        raise HTTPException(status_code=400, detail=FUTWIZ_HELP)

    if parsed.ea_id is None or parsed.base_player_ea_id is None or not parsed.slug:
        raise HTTPException(status_code=400, detail="Linkten kart kimligi cikarilamadi.")

    url = futgg_card_url(
        parsed.base_player_ea_id, parsed.slug, parsed.ea_id, parsed.game or "27"
    )
    try:
        card = await service.add_card_by_ea_id(parsed.ea_id, url)
    except CatalogError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if body.scan_id is not None:
        result = await service.apply_correction(body.scan_id, card.ea_id)
        return service.to_payload(result)

    return {
        "card": {
            "ea_id": card.ea_id,
            "name": card.name,
            "rating": card.rating,
            "version": card.display_version,
        }
    }


@router.post("/catalog/sync")
async def catalog_sync(force: bool = False) -> dict:
    try:
        return await state.require_service().sync_catalog(force=force)
    except CatalogError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
