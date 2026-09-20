"""Shared test fixtures. Nothing here touches the network."""
from __future__ import annotations

import gzip
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).parent / "fixtures"


def load_page(name: str) -> str:
    """Read a saved FUT.GG page (stored gzipped to keep the repo small)."""
    return gzip.decompress((FIXTURES / f"{name}.html.gz").read_bytes()).decode(
        "utf-8", errors="replace"
    )


@pytest.fixture(scope="session")
def zidane_base_icon() -> str:
    """Zidane 94 CAM, 'Base Icon' -- eaId 1397."""
    return load_page("futgg_zidane_base_icon")


@pytest.fixture(scope="session")
def zidane_holographic() -> str:
    """Zidane 94 CAM, 'Base Icon Pristine Holographic' -- eaId 100664693.

    Same name, rating, position, club, nation, league AND rarity name as the
    card above. Only the version label and the eaId differ.
    """
    return load_page("futgg_zidane_holographic")


@pytest.fixture(scope="session")
def mbappe_rare() -> str:
    """Mbappe 91 ST, 'Rare' -- eaId 231747, a player with a single card."""
    return load_page("futgg_mbappe_rare")


@pytest.fixture()
def repo(tmp_path):
    from app.core.db import build_engine
    from app.services.repository import Repository

    engine = build_engine(tmp_path / "test.sqlite3")
    yield Repository(engine)
    engine.dispose()


@pytest.fixture()
def card_factory():
    from app.models.tables import CatalogCard

    def make(
        ea_id: int,
        base: int = 1397,
        name: str = "Zinedine Zidane",
        rating: int | None = 94,
        position: str | None = "CAM",
        version: str | None = "Base Icon",
        rarity: str | None = "Base Icon",
        alt: list[str] | None = None,
    ) -> CatalogCard:
        return CatalogCard(
            ea_id=ea_id,
            base_player_ea_id=base,
            name=name,
            slug=f"{base}-slug",
            url=f"https://www.fut.gg/players/{base}-slug/27-{ea_id}/",
            rating=rating,
            position=position,
            alt_positions=alt or [],
            rarity_name=rarity,
            version_label=version,
            image_url=f"https://img/{ea_id}.webp",
        )

    return make
