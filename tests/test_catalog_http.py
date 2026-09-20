"""Catalog HTTP layer with the network mocked: pagination, retry, failure."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.services.catalog.futgg import SITEMAP_FIRST, CatalogError, FutGGCatalog

BASE = "https://www.fut.gg"


def sitemap(urls: list[str]) -> str:
    body = "".join(f"<loc>{u}</loc>" for u in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset>{body}</urlset>'


PAGE_1 = sitemap([
    f"{BASE}/players/1397-zinedine-zidane/27-1397/",
    f"{BASE}/players/1397-zinedine-zidane/27-100664693/",
    f"{BASE}/players/231747-kylian-mbappe/27-231747/",
    # Entries that are not FC 27 card pages must be ignored.
    f"{BASE}/players/1397-zinedine-zidane/26-1397/",
    f"{BASE}/news/something/",
])
PAGE_2 = sitemap([f"{BASE}/players/158023-lionel-messi/27-158023/"])
EMPTY = sitemap([])


def catalog(**kwargs) -> FutGGCatalog:
    """A catalog client with the politeness delays turned off for tests."""
    kwargs.setdefault("retry_backoff", 0.0)
    kwargs.setdefault("page_delay", 0.0)
    return FutGGCatalog(**kwargs)


def by_page(pages: dict[str, httpx.Response]):
    """Serve a different response per `?p=` value.

    respx ignores a query string that the route pattern does not spell out, so
    separate routes for `?p=2` would all be shadowed by the bare one.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("p", "1")
        return pages.get(page, httpx.Response(404))

    return handler


class TestSitemap:
    @respx.mock
    async def test_parses_and_paginates(self):
        respx.get(SITEMAP_FIRST).mock(
            side_effect=by_page({
                "1": httpx.Response(200, text=PAGE_1),
                "2": httpx.Response(200, text=PAGE_2),
                "3": httpx.Response(200, text=EMPTY),
            })
        )

        async with catalog() as client:
            entries = await client.sitemap_entries()

        assert [e.ea_id for e in entries] == [1397, 100664693, 231747, 158023]
        assert entries[0].base_player_ea_id == 1397
        assert entries[0].slug == "zinedine-zidane"
        assert entries[0].url == f"{BASE}/players/1397-zinedine-zidane/27-1397/"

    @respx.mock
    async def test_ignores_non_card_and_other_game_urls(self):
        respx.get(SITEMAP_FIRST).mock(
            side_effect=by_page({
                "1": httpx.Response(200, text=PAGE_1),
                "2": httpx.Response(200, text=EMPTY),
            })
        )

        async with catalog() as client:
            entries = await client.sitemap_entries()

        assert all(e.ea_id != 26 for e in entries)
        assert len(entries) == 3

    @respx.mock
    async def test_stops_when_a_later_page_is_missing(self):
        respx.get(SITEMAP_FIRST).mock(
            side_effect=by_page({"1": httpx.Response(200, text=PAGE_1)})
        )

        async with catalog() as client:
            entries = await client.sitemap_entries()

        assert len(entries) == 3  # page 1 still counted

    @respx.mock
    async def test_first_page_failure_is_raised(self):
        respx.get(SITEMAP_FIRST).mock(return_value=httpx.Response(404))

        async with catalog() as client:
            with pytest.raises(CatalogError):
                await client.sitemap_entries()


class TestRetry:
    @respx.mock
    async def test_retries_a_transient_server_error(self):
        route = respx.get(SITEMAP_FIRST).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, text=PAGE_2),
                httpx.Response(200, text=EMPTY),
            ]
        )

        async with catalog() as client:
            entries = await client.sitemap_entries()

        assert route.call_count == 3  # failed attempt, page 1, page 2
        assert [e.ea_id for e in entries] == [158023]

    @respx.mock
    async def test_gives_up_after_the_retry_budget(self):
        route = respx.get(SITEMAP_FIRST).mock(return_value=httpx.Response(503))

        async with catalog(max_retries=3) as client:
            with pytest.raises(CatalogError, match="503"):
                await client.sitemap_entries()

        assert route.call_count == 3

    @respx.mock
    async def test_connection_errors_are_retried_then_reported(self):
        respx.get(SITEMAP_FIRST).mock(side_effect=httpx.ConnectError("boom"))

        async with catalog(max_retries=2) as client:
            with pytest.raises(CatalogError, match="okunamadi"):
                await client.sitemap_entries()

    @respx.mock
    async def test_client_errors_are_not_retried(self):
        route = respx.get(SITEMAP_FIRST).mock(return_value=httpx.Response(403))

        async with catalog(max_retries=3) as client:
            with pytest.raises(CatalogError):
                await client.sitemap_entries()

        assert route.call_count == 1, "a 403 will not fix itself"


    @respx.mock
    async def test_a_repeating_server_does_not_cause_an_endless_crawl(self):
        """Every page answering with the same content must terminate."""
        route = respx.get(SITEMAP_FIRST).mock(
            return_value=httpx.Response(200, text=PAGE_1)
        )

        async with catalog(max_pages=10) as client:
            entries = await client.sitemap_entries()

        assert len(entries) == 3, "duplicate cards must not pile up"
        assert route.call_count == 2, "stop as soon as a page adds nothing new"

    @respx.mock
    async def test_max_pages_is_a_hard_stop(self):
        counter = {"n": 0}

        def unique_page(request: httpx.Request) -> httpx.Response:
            counter["n"] += 1
            ea = 1000 + counter["n"]
            return httpx.Response(
                200, text=sitemap([f"{BASE}/players/{ea}-p/27-{ea}/"])
            )

        respx.get(SITEMAP_FIRST).mock(side_effect=unique_page)

        async with catalog(max_pages=5) as client:
            entries = await client.sitemap_entries()

        assert len(entries) == 5


class TestCardPage:
    @respx.mock
    async def test_fetches_and_parses(self, zidane_holographic):
        url = f"{BASE}/players/1397-zinedine-zidane/27-100664693/"
        respx.get(url).mock(return_value=httpx.Response(200, text=zidane_holographic))

        async with catalog() as client:
            page = await client.card_page(url, 100664693)

        assert page.primary.rating == 94
        assert page.primary.version_label == "Base Icon Pristine Holographic"

    async def test_using_the_client_before_entering_fails_clearly(self):
        client = FutGGCatalog()
        with pytest.raises(CatalogError, match="baslatilmadi"):
            await client.card_page("https://www.fut.gg/x/", 1)
