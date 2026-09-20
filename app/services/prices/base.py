"""The PriceProvider interface.

Adding a new source means writing one module that implements `PriceProvider`
and registering it in `app/services/prices/registry.py`. Nothing else changes -- if a
source breaks, only its own file needs editing.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ...models.schemas import Platform, PriceQuote
from ...models.tables import CatalogCard


class PriceUnavailable(Exception):
    """This provider could not produce a price.

    Always raised with a message meant for the user; never swallowed silently.
    A provider raising this lets the chain move on to the next source.
    """

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(f"{source}: {reason}")
        self.source = source
        self.reason = reason


@runtime_checkable
class PriceProvider(Protocol):
    """One price source."""

    name: str
    platform: Platform

    async def fetch(self, card: CatalogCard) -> PriceQuote:
        """Return the lowest BIN for this exact card.

        Raises PriceUnavailable when the price cannot be read.
        """
        ...

    async def aclose(self) -> None:
        """Release any resources (browser, HTTP client)."""
        ...
