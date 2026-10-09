"""FUTNext PC feed tests; all HTTP responses are mocked."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.services.prices.base import PriceUnavailable
from app.services.prices.futnext import PRICE_URL, FutnextProvider


@respx.mock
async def test_fetches_pc_price_for_exact_card(card_factory):
    route = respx.get(PRICE_URL).mock(return_value=httpx.Response(200, json=[
        {"definitionId": 158023, "prices": [97000],
         "updatedAt": int(datetime.now(timezone.utc).timestamp() * 1000)},
    ]))
    provider = FutnextProvider()
    try:
        quote = await provider.fetch(card_factory(158023))
    finally:
        await provider.aclose()

    assert route.call_count == 1
    assert dict(route.calls[0].request.url.params) == {"ids": "158023", "platform": "pc"}
    assert quote.price == 97000
    assert quote.platform == "pc" and quote.source == "futnext"
    assert "platform=pc" in quote.source_url


@pytest.mark.parametrize("records", [
    [],
    [{"definitionId": 1397, "prices": [97000]}],
    [{"definitionId": 158023, "prices": []}],
    [{"definitionId": 158023, "prices": [0]}],
])
@respx.mock
async def test_missing_or_other_card_price_is_unavailable(card_factory, records):
    respx.get(PRICE_URL).mock(return_value=httpx.Response(200, json=records))
    provider = FutnextProvider()
    try:
        with pytest.raises(PriceUnavailable, match="PC fiyati yayinlamiyor"):
            await provider.fetch(card_factory(158023))
    finally:
        await provider.aclose()


@respx.mock
async def test_rate_limit_is_reported_without_crashing(card_factory):
    respx.get(PRICE_URL).mock(return_value=httpx.Response(429))
    provider = FutnextProvider()
    try:
        with pytest.raises(PriceUnavailable, match="HTTP 429"):
            await provider.fetch(card_factory(158023))
    finally:
        await provider.aclose()
