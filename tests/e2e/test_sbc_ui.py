"""Real Chromium DOM -> HTTP -> SBC router -> solver checks."""
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.db import get_session
from app.models.tables import CatalogCard, PriceCache
from app.routers import sbc
from app.routers.club import my_club_inventory


@pytest.fixture(scope="module")
def browser_server():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(sbc.router)
    static = Path(__file__).resolve().parents[2] / "app" / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")
    app.add_api_route("/sbc", lambda: FileResponse(static / "sbc.html"))

    def session_override():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(.05)
    assert server.started
    yield f"http://127.0.0.1:{port}", engine
    server.should_exit = True
    thread.join(timeout=5)
    engine.dispose()


@pytest.fixture
def page_data(browser_server):
    base, engine = browser_server
    my_club_inventory.clear()
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        for definition_id in [100, *range(101, 114)]:
            db.add(CatalogCard(ea_id=definition_id, base_player_ea_id=definition_id,
                               name=f"Card {definition_id}", slug=str(definition_id), url="",
                               rating=84, position="ST"))
            db.add(PriceCache(ea_id=definition_id, platform="pc", source="test", price=1000))
        db.commit()
    for instance_id, definition_id in [("A", 100), ("B", 100), ("C", 100),
                                       *[(f"I{i}", i) for i in range(101, 114)]]:
        my_club_inventory[instance_id] = {"definition_id": str(definition_id),
                                          "untradeable": False, "item_score": 10}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(base + "/sbc")
        yield page, engine
        browser.close()


def solve(page):
    page.locator("#sbc-solve-btn").click()
    page.locator("#sbc-validity").get_by_text("VALID", exact=True).wait_for(timeout=20000)
    return page.locator(".sol-card")


def test_solve_swap_lock_undo_and_instance_identity(page_data):
    page, _ = page_data
    requests = []
    verifications = []
    page.on("request", lambda request: requests.append(request.post_data_json)
            if request.url.endswith("/api/sbc/swap") else None)
    page.on("request", lambda request: verifications.append(request.post_data_json)
            if request.url.endswith("/api/sbc/verify") else None)
    rows = solve(page)
    assert rows.count() == 11
    selected = [r.get_attribute("data-instance-id") for r in rows.all()]
    assert len(selected) == len(set(selected))
    assert len(set(selected) & {"A", "B", "C"}) >= 2
    original = selected[0]
    original_rating = int(rows.first.locator("span").first.inner_text().split()[0])
    rows.first.get_by_text("Lock").click()
    assert rows.first.get_by_text("Unlock").is_visible()
    solve(page)
    assert page.locator(f'.sol-card[data-instance-id="{original}"]').get_by_text("Unlock").is_visible()
    page.locator(f'.sol-card[data-instance-id="{original}"]').get_by_text("Swap").click()
    assert requests[-1]["original_instance_id"] == original
    candidates = page.locator("#swap-candidates button")
    candidates.first.wait_for(timeout=15000)
    candidate_id = candidates.first.get_attribute("data-instance-id")
    assert int(candidates.first.inner_text().split()[0]) == original_rating
    candidates.first.click()
    page.locator("#sbc-validity").get_by_text("VALID", exact=True).wait_for()
    assert page.locator(f'.sol-card[data-instance-id="{candidate_id}"]').count() == 1
    page.locator("#undo-btn").click()
    page.locator("#sbc-validity").get_by_text("VALID", exact=True).wait_for()
    assert page.locator(f'.sol-card[data-instance-id="{original}"]').count() == 1
    assert len(verifications) >= 5  # solve, lock, re-solve, swap, undo


def test_streamlined_score_and_stale_validity(page_data):
    page, _ = page_data
    page.locator("#sbc-mode").select_option("STREAMLINED")
    page.locator("#sbc-target-score").fill("100")
    rows = solve(page)
    assert rows.count() == 10
    assert "100 / 100" in page.locator("#res-score").inner_text()
    page.locator("#sbc-target-score").fill("1000")
    page.locator("#sbc-target-score").dispatch_event("change")
    page.locator("#sbc-validity").get_by_text("INVALID", exact=True).wait_for()


def test_completion_count_reaches_joint_solver(page_data):
    page, _ = page_data
    requests = []
    page.on("request", lambda request: requests.append(request.post_data_json)
            if request.url.endswith("/api/sbc/solve") else None)
    page.locator("#sbc-mode").select_option("STREAMLINED")
    page.locator("#sbc-target-score").fill("10")
    page.locator("#completion-count").fill("2")
    solve(page)
    assert requests[-1]["completion_count"] == 2
    assert "2 / 2" in page.locator("#res-completions").inner_text()


def test_settings_change_solver_selection(page_data):
    page, engine = page_data
    solve_requests = []
    page.on("request", lambda request: solve_requests.append(request.post_data_json)
            if request.url.endswith("/api/sbc/solve") else None)
    with Session(engine) as db:
        trade = db.get(CatalogCard, 112)
        untrade = db.get(CatalogCard, 113)
        assert trade and untrade
        db.exec(__import__('sqlmodel').select(PriceCache).where(PriceCache.ea_id == 112)).first().price = 1000
        db.exec(__import__('sqlmodel').select(PriceCache).where(PriceCache.ea_id == 113)).first().price = 5000
        db.commit()
    my_club_inventory["I113"]["untradeable"] = True
    for key in list(my_club_inventory):
        if key not in {"I112", "I113", "A", "B", "C", *[f"I{i}" for i in range(101, 108)]}:
            del my_club_inventory[key]
    solve(page)
    selected_prefer = {r.get_attribute("data-instance-id") for r in page.locator(".sol-card").all()}
    assert "I113" in selected_prefer and "I112" not in selected_prefer
    assert solve_requests[-1]["prefer_untradeable"] is True
    page.locator("#prefer-untradeable").uncheck()
    solve(page)
    selected_no_prefer = {r.get_attribute("data-instance-id") for r in page.locator(".sol-card").all()}
    assert "I112" in selected_no_prefer and "I113" not in selected_no_prefer
    assert solve_requests[-1]["prefer_untradeable"] is False
    with Session(engine) as db:
        for card_id in range(101, 114):
            quote = db.exec(__import__('sqlmodel').select(PriceCache).where(PriceCache.ea_id == card_id)).first()
            if quote:
                quote.price = 60000
        db.commit()
    page.locator("#protect-expensive").check()
    page.locator("#sbc-solve-btn").click()
    page.locator("#sbc-validity").get_by_text("INFEASIBLE", exact=True).wait_for(timeout=20000)
    assert solve_requests[-1]["protect_expensive"] is True
    page.locator("#protect-expensive").uncheck()
    solve(page)
    assert solve_requests[-1]["protect_expensive"] is False
