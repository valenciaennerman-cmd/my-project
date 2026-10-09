import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from app.main import app
from app.core.db import get_session
from app.models.tables import CatalogCard, PriceCache
from app.routers.club import my_club_inventory

from sqlalchemy.pool import StaticPool

# Create test db
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SQLModel.metadata.create_all(engine)

def override_get_session():
    with Session(engine) as session:
        yield session

app.dependency_overrides[get_session] = override_get_session
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    my_club_inventory.clear()

    with Session(engine) as session:
        # Add some cards
        for i in range(1, 20):
            rating = 84
            price = 5000 if i < 15 else 60000 # Make some expensive
            c = CatalogCard(ea_id=i, base_player_ea_id=i, name=f"Player {i}", slug=f"player-{i}", url="", rating=rating, position="ST")
            pc = PriceCache(ea_id=i, platform="pc", source="futbin", price=price)
            session.add(c)
            session.add(pc)
        session.commit()

        # Add to club
        for i in range(1, 20):
            my_club_inventory[str(i)] = False # Tradeable

def test_solve_endpoint():
    res = client.post("/api/sbc/solve", json={
        "min_rating": 84,
        "protect_expensive": True,
        "prefer_untradeable": True,
        "completion_count": 1
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    squad = data["squad"]
    assert len(squad) == 11

    # Check protect_expensive works
    for p in squad:
        assert p["price"] <= 50000

def test_solve_with_locked_players():
    # Lock an expensive player that would normally be protected
    res = client.post("/api/sbc/solve", json={
        "min_rating": 84,
        "protect_expensive": True,
        "prefer_untradeable": True,
        "completion_count": 1,
        "locked_players": [{"definition_id": "16", "ea_id": 16, "name": "Player 16", "rating": 84, "locked": True}]
    })
    assert res.status_code == 200
    data = res.json()
    squad = data["squad"]

    locked_p = next((p for p in squad if str(p["ea_id"]) == "16"), None)
    assert locked_p is not None
    assert locked_p["price"] == 60000 # expensive, but included because it was locked

def test_swap_endpoint():
    res = client.post("/api/sbc/solve", json={"min_rating": 84, "protect_expensive": True, "prefer_untradeable": True})
    squad = res.json()["squad"]

    original_id = str(squad[0]["ea_id"])

    swap_res = client.post("/api/sbc/swap", json={
        "current_squad": squad,
        "original_definition_id": original_id,
        "min_rating": 84,
        "protect_expensive": True
    })

    assert swap_res.status_code == 200
    assert "results" in swap_res.json()


def test_physical_instances_survive_api_and_forged_properties_are_ignored():
    my_club_inventory.clear()
    for instance_id in ("A", "B", "C"):
        my_club_inventory[instance_id] = {"definition_id": "1", "untradeable": False, "item_score": 10}
    for definition_id in range(2, 10):
        my_club_inventory[f"I{definition_id}"] = {"definition_id": str(definition_id),
                                                      "untradeable": False, "item_score": 10}
    response = client.post("/api/sbc/solve", json={"min_rating": 84,
        "locked_players": [{"instance_id": key} for key in ("A", "B", "C")]})
    assert response.status_code == 200
    squad = response.json()["squad"]
    assert {"A", "B", "C"}.issubset({p["instance_id"] for p in squad})
    forged = [dict(p, rating=99) for p in squad]
    verification = client.post("/api/sbc/verify", json={"squad": forged, "min_rating": 99}).json()["verification"]
    assert verification["valid"] is False
    del my_club_inventory["A"]
    stale = client.post("/api/sbc/verify", json={"squad": squad, "min_rating": 84}).json()["verification"]
    assert stale["valid"] is False
