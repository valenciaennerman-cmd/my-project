"""Price chain behaviour: cache, fallback order, and PC-vs-console selection.

No network: providers are fakes and the FUTWIZ DOM payloads are the shapes the
real page produced when this was measured.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.schemas import PriceQuote
from app.services.prices.base import PriceUnavailable
from app.services.prices.chain import PriceService
from app.services.prices.futwiz import FutwizProvider
from app.services.prices.registry import BUILDERS, build_providers


def quote(price: int | None, source: str, platform: str = "pc", age: float = 0.0):
    return PriceQuote(
        ea_id=1397,
        price=price,
        platform=platform,  # type: ignore[arg-type]
        source=source,
        fetched_at=datetime.now(timezone.utc) - timedelta(seconds=age),
        source_url=f"https://{source}/x",
    )


class FakeProvider:
    def __init__(self, name: str, platform: str, result=None, error: str | None = None):
        self.name = name
        self.platform = platform
        self._result = result
        self._error = error
        self.calls = 0

    async def fetch(self, card):
        self.calls += 1
        if self._error is not None:
            raise PriceUnavailable(self.name, self._error)
        return self._result

    async def aclose(self) -> None:
        return None


class BoomProvider(FakeProvider):
    async def fetch(self, card):
        self.calls += 1
        raise ZeroDivisionError("unexpected")


@pytest.fixture()
def card(card_factory):
    return card_factory(1397)


class TestChain:
    async def test_first_provider_wins(self, repo, card):
        pc = FakeProvider("futwiz", "pc", quote(2_850_000, "futwiz"))
        console = FakeProvider("futgg", "console", quote(1_370_000, "futgg", "console"))
        service = PriceService([pc, console], repo)

        result, failures = await service.get(card)

        assert result.price == 2_850_000
        assert result.platform == "pc"
        assert failures == []
        assert console.calls == 0, "fallback must not run when the primary worked"

    async def test_falls_back_and_reports_why(self, repo, card):
        pc = FakeProvider("futwiz", "pc", error="Bot dogrulamasi gecilemedi")
        console = FakeProvider("futgg", "console", quote(1_370_000, "futgg", "console"))
        service = PriceService([pc, console], repo)

        result, failures = await service.get(card)

        assert result.price == 1_370_000
        assert result.platform == "console"
        assert [f.source for f in failures] == ["futwiz"]
        assert "Bot dogrulamasi" in failures[0].reason

    async def test_all_fail_returns_none_with_every_reason(self, repo, card):
        service = PriceService(
            [
                FakeProvider("futwiz", "pc", error="challenge"),
                FakeProvider("futgg", "console", error="no price node"),
            ],
            repo,
        )
        result, failures = await service.get(card)

        assert result is None
        assert {f.source for f in failures} == {"futwiz", "futgg"}

    async def test_unexpected_error_is_captured_not_raised(self, repo, card):
        """One broken provider must never kill the scan."""
        service = PriceService(
            [BoomProvider("futwiz", "pc"), FakeProvider("futgg", "console", quote(5, "futgg", "console"))],
            repo,
        )
        result, failures = await service.get(card)

        assert result.price == 5
        assert "ZeroDivisionError" in failures[0].reason

    async def test_cache_short_circuits(self, repo, card):
        provider = FakeProvider("futwiz", "pc", quote(2_850_000, "futwiz"))
        service = PriceService([provider], repo, cache_ttl=600)

        await service.get(card)
        second, _ = await service.get(card)

        assert provider.calls == 1
        assert second.price == 2_850_000

    async def test_force_refresh_bypasses_cache(self, repo, card):
        provider = FakeProvider("futwiz", "pc", quote(2_850_000, "futwiz"))
        service = PriceService([provider], repo, cache_ttl=600)

        await service.get(card)
        await service.get(card, force_refresh=True)

        assert provider.calls == 2

    async def test_expired_cache_refetches(self, repo, card):
        provider = FakeProvider("futwiz", "pc", quote(2_850_000, "futwiz"))
        service = PriceService([provider], repo, cache_ttl=1)

        await service.get(card)
        repo.store_price(
            ea_id=card.ea_id, platform="pc", source="futwiz", price=1,
            is_extinct=False, note=None, source_url=None,
            fetched_at=datetime.now(timezone.utc) - timedelta(seconds=300),
        )
        result, _ = await service.get(card)

        assert provider.calls == 2
        assert result.price == 2_850_000

    async def test_stale_cache_beats_nothing_when_every_source_fails(self, repo, card):
        repo.store_price(
            ea_id=card.ea_id, platform="pc", source="futwiz", price=2_000_000,
            is_extinct=False, note="eski", source_url=None,
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        service = PriceService(
            [FakeProvider("futwiz", "pc", error="challenge")], repo, cache_ttl=60
        )
        result, failures = await service.get(card)

        assert result is not None and result.price == 2_000_000
        assert result.age_seconds > 3000, "the UI must be able to show it is stale"
        assert failures, "the failure is still reported alongside the stale value"

    async def test_quote_is_persisted_for_next_time(self, repo, card):
        service = PriceService([FakeProvider("futwiz", "pc", quote(123, "futwiz"))], repo)
        await service.get(card)

        row = repo.cached_price(card.ea_id, "pc")
        assert row is not None and row.price == 123 and row.source == "futwiz"

    def test_provider_names_are_exposed(self, repo):
        service = PriceService(
            [FakeProvider("futwiz", "pc"), FakeProvider("futgg", "console")], repo
        )
        assert service.provider_names == ["futwiz", "futgg"]


class TestRegistry:
    def test_known_providers(self):
        assert set(BUILDERS) == {"futwiz", "futgg"}

    def test_unknown_provider_fails_loudly(self, repo):
        with pytest.raises(ValueError, match="Bilinmeyen fiyat kaynagi"):
            build_providers(("nope",), pool=None, repo=repo)  # type: ignore[arg-type]

    def test_order_is_preserved(self, repo):
        providers = build_providers(("futgg", "futwiz"), pool=None, repo=repo)  # type: ignore[arg-type]
        assert [p.name for p in providers] == ["futgg", "futwiz"]


class TestFutwizPlatformPick:
    """PC and console are separate markets; picking the wrong block is the
    single most damaging bug this tool could have."""

    @pytest.fixture()
    def provider(self, repo):
        return FutwizProvider(pool=None, repo=repo)  # type: ignore[arg-type]

    def test_picks_the_block_labelled_pc(self, provider):
        blocks = [
            {"price": "1,370,000", "icons": ["playstation"], "hasPcLabel": False,
             "cls": "text-cyan-300", "age": "3 mins ago"},
            {"price": "2,850,000", "icons": ["computer"], "hasPcLabel": True,
             "cls": "text-orange-400", "age": "1 hour ago"},
        ]
        price, age = provider._pick_pc(blocks)
        assert price == 2_850_000
        assert age == "1 hour ago"

    def test_picks_pc_even_when_it_is_listed_first(self, provider):
        blocks = [
            {"price": "2,850,000", "icons": ["computer"], "hasPcLabel": True, "cls": "", "age": None},
            {"price": "1,370,000", "icons": ["playstation"], "hasPcLabel": False, "cls": "", "age": None},
        ]
        assert provider._pick_pc(blocks)[0] == 2_850_000

    def test_colour_is_only_a_last_resort(self, provider):
        blocks = [
            {"price": "1,370,000", "icons": [], "hasPcLabel": False, "cls": "text-cyan-300", "age": None},
            {"price": "2,850,000", "icons": [], "hasPcLabel": False, "cls": "text-orange-400", "age": None},
        ]
        assert provider._pick_pc(blocks)[0] == 2_850_000

    def test_pricing_unavailable_is_a_real_answer(self, provider):
        """FUTWIZ prints this where it has no PC data; it is not a read failure."""
        blocks = [
            {"price": "6,000,000", "icons": ["xbox", "playstation"], "hasPcLabel": False,
             "cls": "text-cyan-300", "age": "3 days ago", "unavailable": False},
            {"price": None, "icons": ["computer"], "hasPcLabel": True,
             "cls": "", "age": None, "unavailable": True,
             "text": "PC | Pricing unavailable at this time"},
        ]
        block = provider._pc_block(blocks)
        assert block is not None and block["unavailable"] is True
        # ...and it must never be mistaken for the console figure next to it.
        assert block["price"] is None

    def test_no_pc_block_returns_nothing_rather_than_a_console_price(self, provider):
        blocks = [
            {"price": "1,370,000", "icons": ["playstation"], "hasPcLabel": False,
             "cls": "text-cyan-300", "age": None},
        ]
        assert provider._pick_pc(blocks) == (None, None)

    def test_empty_page(self, provider):
        assert provider._pick_pc([]) == (None, None)
        assert provider._pc_block([]) is None

    @pytest.mark.parametrize(
        "text, expected",
        [("1,370,000", 1370000), ("2.850.000", 2850000), ("12,250", 12250), ("", None)],
    )
    def test_number_parsing(self, provider, text, expected):
        blocks = [{"price": text, "icons": ["computer"], "hasPcLabel": True, "cls": "", "age": None}]
        assert provider._pick_pc(blocks)[0] == expected

    @pytest.mark.parametrize(
        "text, rating",
        [("Zinedine Zidane CAM| 94", 94), ("Luca Zidane GK| 68", 68), ("no digits", None)],
    )
    def test_rating_from_search_row(self, provider, text, rating):
        assert provider._rating_in(text) == rating

    @pytest.mark.parametrize(
        "text, position",
        [("Zinedine Zidane CAM| 94", "CAM"), ("Luca Zidane GK| 68", "GK"), ("nothing", None)],
    )
    def test_position_from_search_row(self, provider, text, position):
        assert provider._position_in(text) == position
