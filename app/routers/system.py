"""Status, the SSE stream, and the capture on/off switches."""
from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core.config import settings
from ..core.state import state

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


class CaptureBody(BaseModel):
    enabled: bool


@router.get("/api/status")
async def status() -> dict:
    repo = state.require_repo()
    return {
        "watcher": state.folder.status() if state.folder else {},
        "clipboard": state.clipboard.status() if state.clipboard else {},
        "catalog": {
            "status": state.require_service().catalog_status,
            "players": repo.player_count(),
            "cards": repo.card_count(),
        },
        "vision": {
            "ready": state.vision_ready,
            "backend": settings.vision_backend,
            "model": state.reader.model if state.reader else None,
            "error": state.vision_error,
        },
        "prices": {
            "providers": state.prices.provider_names if state.prices else [],
            "cache_ttl": settings.price_cache_ttl,
        },
        "ea_tax_rate": settings.ea_tax_rate,
    }


@router.get("/api/events")
async def events() -> StreamingResponse:
    queue = state.bus.subscribe()
    return StreamingResponse(
        state.bus.stream(queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/watch")
async def set_watch(body: CaptureBody) -> dict:
    if state.folder is None:
        return {}
    state.folder.resume() if body.enabled else state.folder.pause()
    status = state.folder.status()
    state.bus.publish("watcher", status)
    return status


@router.post("/api/clipboard")
async def set_clipboard(body: CaptureBody) -> dict:
    if state.clipboard is None:
        return {}
    state.clipboard.resume() if body.enabled else state.clipboard.pause()
    status = state.clipboard.status()
    state.bus.publish("clipboard", status)
    return status
