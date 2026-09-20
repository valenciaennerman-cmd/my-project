"""Scan history, thumbnails, manual corrections and price refresh."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.state import state
from ..services.catalog.futgg import CatalogError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scans", tags=["scans"])


class CorrectionBody(BaseModel):
    ea_id: int


@router.get("")
async def list_scans(limit: int = Query(default=25, ge=1, le=100)) -> dict:
    return {"scans": state.require_repo().recent_scans(limit)}


@router.get("/{scan_id}/image")
async def scan_image(scan_id: int) -> FileResponse:
    scan = state.require_repo().get_scan(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Tarama bulunamadi.")
    path = Path(scan.image_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Ekran goruntusu dosyasi yok.")
    return FileResponse(path)


@router.post("/{scan_id}/correct")
async def correct(scan_id: int, body: CorrectionBody) -> dict:
    service = state.require_service()
    try:
        result = await service.apply_correction(scan_id, body.ea_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CatalogError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return service.to_payload(result)


@router.post("/{scan_id}/refresh")
async def refresh(scan_id: int) -> dict:
    service = state.require_service()
    try:
        result = await service.refresh_price(scan_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.to_payload(result)
