"""Process-wide singletons, built once in the app lifespan.

Routers read from here instead of importing each other, so wiring lives in
exactly one place.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.engine import Engine

from ..services.ingest.clipboard import ClipboardWatcher
from ..services.ingest.folder import FolderWatcher
from ..services.prices.browser import BrowserPool
from ..services.prices.chain import PriceService
from ..services.recognize.base import CardReader
from ..services.repository import Repository
from ..services.scan_service import ScanService
from .events import EventBus


@dataclass
class AppState:
    engine: Engine | None = None
    repo: Repository | None = None
    bus: EventBus = field(default_factory=EventBus)
    pool: BrowserPool | None = None
    prices: PriceService | None = None
    reader: CardReader | None = None
    service: ScanService | None = None
    folder: FolderWatcher | None = None
    clipboard: ClipboardWatcher | None = None
    vision_ready: bool = False
    vision_error: str | None = None

    def require_service(self) -> ScanService:
        if self.service is None:
            raise RuntimeError("Uygulama henuz baslatilmadi.")
        return self.service

    def require_repo(self) -> Repository:
        if self.repo is None:
            raise RuntimeError("Veritabani henuz baslatilmadi.")
        return self.repo


state = AppState()
