"""Card-link parsing: getting the version id out of a pasted URL."""
from __future__ import annotations

import pytest

from app.services.matching.links import (
    LinkError,
    futgg_card_url,
    futwiz_card_url,
    parse_card_link,
)


class TestFutGG:
    def test_extracts_ea_id_not_base_player_id(self):
        link = parse_card_link("https://www.fut.gg/players/1397-zinedine-zidane/27-100664693/")
        assert link.kind == "futgg"
        assert link.ea_id == 100664693          # the card
        assert link.base_player_ea_id == 1397   # the player
        assert link.slug == "zinedine-zidane"
        assert link.game == "27"
        assert link.resolvable

    def test_base_card_where_ea_id_equals_player_id(self):
        link = parse_card_link("https://www.fut.gg/players/1397-zinedine-zidane/27-1397/")
        assert link.ea_id == 1397
        assert link.base_player_ea_id == 1397

    def test_two_zidane_links_give_different_ids(self):
        """The whole point: same name and slug, different card."""
        a = parse_card_link("https://www.fut.gg/players/1397-zinedine-zidane/27-1397/")
        b = parse_card_link("https://www.fut.gg/players/1397-zinedine-zidane/27-100664693/")
        assert a.slug == b.slug
        assert a.ea_id != b.ea_id

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.fut.gg/players/1397-zinedine-zidane/27-1397/",
            "http://www.fut.gg/players/1397-zinedine-zidane/27-1397/",
            "www.fut.gg/players/1397-zinedine-zidane/27-1397/",
            "  https://www.fut.gg/players/1397-zinedine-zidane/27-1397/?utm=x  ",
        ],
    )
    def test_tolerates_url_shapes(self, url):
        assert parse_card_link(url).ea_id == 1397


class TestFutwiz:
    def test_extracts_site_id(self):
        link = parse_card_link("https://www.futwiz.com/en/fc27/player/zinedine-zidane/111561")
        assert link.kind == "futwiz"
        assert link.site_id == 111561
        assert link.slug == "zinedine-zidane"
        # FUTWIZ numbers cards itself, so no EA id can be read from the URL.
        assert link.ea_id is None
        assert link.resolvable

    def test_language_prefix_is_optional(self):
        assert parse_card_link(
            "https://www.futwiz.com/fc27/player/andres-iniesta/111581"
        ).site_id == 111581


class TestFutbin:
    def test_recognised_but_not_resolvable(self):
        """FUTBIN is unreachable, so we recognise the link and say so."""
        link = parse_card_link("https://www.futbin.com/27/player/21491/zidane")
        assert link.kind == "futbin"
        assert link.site_id == 21491
        assert link.ea_id is None
        assert not link.resolvable

    def test_the_two_example_zidanes_are_distinct_ids(self):
        a = parse_card_link("https://www.futbin.com/27/player/21491/zidane")
        b = parse_card_link("https://www.futbin.com/27/player/21493/zidane")
        assert a.site_id != b.site_id

    def test_slug_is_optional(self):
        assert parse_card_link("https://www.futbin.com/27/player/21491").site_id == 21491


class TestRejections:
    @pytest.mark.parametrize(
        "text",
        ["", "   ", "not a url", "https://example.com/players/1-x/27-2/",
         "https://www.fut.gg/players/", "https://futbin.com/", "zidane"],
    )
    def test_raises_link_error(self, text):
        with pytest.raises(LinkError):
            parse_card_link(text)

    def test_error_message_tells_the_user_what_to_do(self):
        with pytest.raises(LinkError, match="FUT.GG"):
            parse_card_link("https://example.com/nope")


class TestUrlBuilders:
    def test_futgg_round_trip(self):
        url = futgg_card_url(1397, "zinedine-zidane", 100664693)
        assert parse_card_link(url).ea_id == 100664693

    def test_futwiz_round_trip(self):
        url = futwiz_card_url("zinedine-zidane", 111561)
        assert parse_card_link(url).site_id == 111561
