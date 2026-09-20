"""Where price sources are wired up.

To add a source: write a module implementing `PriceProvider`, then add one line
to `BUILDERS` below and put its name in `PRICE_PROVIDERS` in `.env`.
"""
from __future__ import annotations

from typing import Callable

from ..repository import Repository
from .base import PriceProvider
from .browser import BrowserPool
from .futgg import FutGGPriceProvider
from .futwiz import FutwizProvider

BUILDERS: dict[str, Callable[[BrowserPool, Repository], PriceProvider]] = {
    "futwiz": lambda pool, repo: FutwizProvider(pool, repo),
    "futgg": lambda pool, repo: FutGGPriceProvider(pool),
}


def build_providers(
    names: tuple[str, ...], pool: BrowserPool, repo: Repository
) -> list[PriceProvider]:
    """Instantiate providers in the configured order, skipping unknown names."""
    providers: list[PriceProvider] = []
    for name in names:
        builder = BUILDERS.get(name)
        if builder is None:
            raise ValueError(
                f"Bilinmeyen fiyat kaynagi: {name!r}. "
                f"Tanimli olanlar: {', '.join(sorted(BUILDERS))}"
            )
        providers.append(builder(pool, repo))
    return providers
