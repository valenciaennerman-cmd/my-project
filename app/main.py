"""FastAPI entry point: wires the services together and serves the local UI."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .core.config import settings
from .core.db import build_engine
from .core.logging import setup_logging
from .core.state import state
from .routers import catalog as catalog_router
from .routers import history as history_router
from .routers import scans as scans_router
from .routers import system as system_router
from .routers import favorites as fav_router
from .routers import club as club_router
from .routers import tcp as tcp_router
from .services.catalog.futgg import CatalogError
from .services.ingest.clipboard import ClipboardWatcher
from .services.ingest.folder import FolderWatcher
from .services.prices.browser import BrowserPool
from .services.prices.chain import PriceService
from .services.prices.registry import build_providers
from .services.recognize.base import VisionError
from .services.recognize.registry import build_reader
from .services.repository import Repository
from .services.scan_service import ScanService
from .services.telegram_bot import TelegramBot
from app.services.feeder import feeder

logger = logging.getLogger("fc27")

STATIC_DIR = Path(__file__).parent / "static"


async def _handle_folder_file(path: Path) -> None:
    await state.require_service().process_file(path, source="folder")


async def _handle_clipboard_file(path: Path) -> None:
    await state.require_service().process_file(path, source="clipboard")


async def _startup_catalog() -> None:
    try:
        await state.require_service().sync_catalog()
    except CatalogError as exc:
        logger.error("katalog senkronizasyonu basarisiz: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    state.engine = build_engine(settings.db_path)
    state.repo = Repository(state.engine)

    state.pool = BrowserPool(
        profile_dir=settings.browser_profile_dir,
        min_interval=settings.browser_min_interval,
        challenge_timeout=settings.browser_challenge_timeout,
        headless=settings.browser_headless,
        offscreen=settings.browser_offscreen,
    )
    state.prices = PriceService(
        build_providers(settings.provider_order, state.pool, state.repo),
        state.repo,
        cache_ttl=settings.price_cache_ttl,
    )

    # Yapay zeka modulleri (Ollama vb.) kullanilmadigi icin devre disi birakildi.
    state.reader = None
    state.vision_ready = False
    state.vision_error = "Yapay zeka (Gorsel okuma) kullanici talebi uzerine kapatildi."

    state.service = ScanService(
        repo=state.repo,
        bus=state.bus,
        reader=state.reader,
        prices=state.prices,
        ea_tax_rate=settings.ea_tax_rate,
    )

    state.telegram = TelegramBot(token=settings.telegram_token, chat_id=settings.telegram_chat_id, service=state.service)
    state.telegram.start()

    state.folder = FolderWatcher(
        directory=settings.watch_dir,
        extensions=settings.extensions,
        on_new_file=_handle_folder_file,
    )
    state.folder.start()

    state.clipboard = ClipboardWatcher(
        inbox=settings.inbox_dir,
        on_new_file=_handle_clipboard_file,
        poll_interval=settings.clipboard_poll_interval,
        enabled=settings.clipboard_enabled,
    )
    state.clipboard.start()

    asyncio.create_task(_startup_catalog(), name="catalog-sync")
    await feeder.start()

    logger.info("hazir -> http://%s:%s", settings.host, settings.port)
    try:
        yield
    finally:
        if state.folder:
            await state.folder.stop()
        if state.clipboard:
            await state.clipboard.stop()
        await feeder.stop()
        if state.prices:
            await state.prices.aclose()
        if state.pool:
            await state.pool.aclose()
        if state.telegram:
            await state.telegram.aclose()
        if state.reader:
            await state.reader.aclose()
        if state.engine:
            state.engine.dispose()
        logger.info("kapatildi")


app = FastAPI(title="FC 27 Fiyat Araci", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system_router.router)
app.include_router(scans_router.router)
app.include_router(catalog_router.router)
app.include_router(history_router.router)
app.include_router(fav_router.router)
app.include_router(club_router.router)
app.include_router(tcp_router.router)
from .routers import sbc as sbc_router
from .routers import portfolio as portfolio_router
app.include_router(sbc_router.router)
app.include_router(portfolio_router.router)




@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/squad", include_in_schema=False)
async def squad() -> FileResponse:
    return FileResponse(STATIC_DIR / "squad.html")

@app.get("/tcp", include_in_schema=False)
async def tcp() -> FileResponse:
    return FileResponse(STATIC_DIR / "tcp.html")

@app.get("/favorites", include_in_schema=False)
async def favorites() -> FileResponse:
    return FileResponse(STATIC_DIR / "favorites.html")


@app.get("/calculator", include_in_schema=False)
async def calculator() -> FileResponse:
    return FileResponse(STATIC_DIR / "calculator.html")

@app.get("/sbc")
async def sbc_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "sbc.html")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
