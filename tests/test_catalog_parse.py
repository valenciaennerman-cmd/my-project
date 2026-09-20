"""Parsing real FUT.GG pages -- no network, fixtures are saved responses.

The Zidane pair is the important case: two cards that agree on everything the
naive approach would key on.
"""
from __future__ import annotations

import pytest

from app.services.catalog.futgg import card_url, parse_card_page
from app.services.catalog.serial import objects_in_array, scalar, string_list


class TestZidanePair:
    def test_base_icon_fields(self, zidane_base_icon):
        card = parse_card_page(zidane_base_icon, 1397).primary
        assert card.ea_id == 1397
        assert card.name == "Zinedine Zidane"
        assert card.rating == 94
        assert card.position == "CAM"
        assert card.alt_positions == ["CM"]
        assert card.rarity_name == "Base Icon"
        assert card.version_label == "Base Icon"
        assert card.base_player_ea_id == 1397

    def test_holographic_fields(self, zidane_holographic):
        card = parse_card_page(zidane_holographic, 100664693).primary
        assert card.ea_id == 100664693
        assert card.rating == 94
        assert card.position == "CAM"
        # Same rarity as the base card...
        assert card.rarity_name == "Base Icon"
        # ...but the version label is what actually separates them.
        assert card.version_label == "Base Icon Pristine Holographic"
        assert "Holographic" in card.version_label

    def test_the_pair_is_identical_except_for_id_and_version(
        self, zidane_base_icon, zidane_holographic
    ):
        a = parse_card_page(zidane_base_icon, 1397).primary
        b = parse_card_page(zidane_holographic, 100664693).primary

        assert (a.name, a.rating, a.position, a.alt_positions, a.rarity_name) == (
            b.name, b.rating, b.position, b.alt_positions, b.rarity_name
        )
        assert a.ea_id != b.ea_id
        assert a.version_label != b.version_label

    def test_artwork_urls_are_per_card(self, zidane_base_icon, zidane_holographic):
        """The picker shows images, so they must not collide."""
        a = parse_card_page(zidane_base_icon, 1397).primary
        b = parse_card_page(zidane_holographic, 100664693).primary
        assert a.image_url and b.image_url
        assert a.image_url != b.image_url

    def test_holographic_sibling_is_discovered(self, zidane_base_icon):
        """FUT.GG keeps holographic variants out of the version list."""
        page = parse_card_page(zidane_base_icon, 1397)
        assert 100664693 in page.variant_ea_ids

    def test_other_versions_are_listed(self, zidane_base_icon):
        page = parse_card_page(zidane_base_icon, 1397)
        ratings = {s.rating for s in page.siblings}
        assert 86 in ratings
        assert all(s.ea_id != 1397 for s in page.siblings)


class TestSinglePlayer:
    def test_mbappe(self, mbappe_rare):
        page = parse_card_page(mbappe_rare, 231747)
        card = page.primary
        assert card.name == "Kylian Mbappé"
        assert card.rating == 91
        assert card.position == "ST"
        assert card.alt_positions == ["LW"]
        assert card.version_label == "Rare"
        assert card.base_player_ea_id == 231747

    def test_no_phantom_siblings(self, mbappe_rare):
        page = parse_card_page(mbappe_rare, 231747)
        assert all(s.ea_id != 231747 for s in page.siblings)


class TestCardUrl:
    """A duplicated id in the slug ("231747-231747-kylian-mbappe") made every
    generated link 404, so both slug conventions are accepted."""

    @pytest.mark.parametrize(
        "base, slug, ea_id, expected",
        [
            (231747, "231747-kylian-mbappe", 231747,
             "https://www.fut.gg/players/231747-kylian-mbappe/27-231747/"),
            (231747, "kylian-mbappe", 231747,
             "https://www.fut.gg/players/231747-kylian-mbappe/27-231747/"),
            (1397, "1397-zinedine-zidane", 100664693,
             "https://www.fut.gg/players/1397-zinedine-zidane/27-100664693/"),
            (1397, "zinedine-zidane", 100664693,
             "https://www.fut.gg/players/1397-zinedine-zidane/27-100664693/"),
        ],
    )
    def test_both_slug_conventions(self, base, slug, ea_id, expected):
        assert card_url(base, slug, ea_id) == expected

    def test_parsed_pages_produce_fetchable_urls(
        self, mbappe_rare, zidane_holographic
    ):
        for html, ea_id in ((mbappe_rare, 231747), (zidane_holographic, 100664693)):
            url = parse_card_page(html, ea_id).primary.url
            assert "//" not in url.split("://", 1)[1], url
            slug_part = url.split("/players/")[1].split("/")[0]
            assert slug_part.count("-") >= 1
            # the id must appear exactly once at the front of the slug
            assert not slug_part.startswith(f"{slug_part.split('-')[0]}-{slug_part.split('-')[0]}-")


class TestSerialReader:
    def test_scalar_types(self):
        block = '{eaId:1397,overall:94,name:"Zidane",isIcon:!0,isHero:!1,price:null}'
        assert scalar(block, "eaId") == 1397
        assert scalar(block, "overall") == 94
        assert scalar(block, "name") == "Zidane"
        assert scalar(block, "isIcon") is True
        assert scalar(block, "isHero") is False
        assert scalar(block, "price") is None
        assert scalar(block, "missing") is None

    def test_scalar_does_not_match_a_key_suffix(self):
        """`basePlayerEaId` must not satisfy a lookup for `eaId`."""
        block = "{basePlayerEaId:1397,eaId:100664693}"
        assert scalar(block, "eaId") == 100664693

    def test_string_list_handles_back_reference_prefix(self):
        assert string_list('{alternativePositions:$R[55]=["CM","LW"]}', "alternativePositions") == ["CM", "LW"]
        assert string_list('{alternativePositions:["CM"]}', "alternativePositions") == ["CM"]
        assert string_list("{alternativePositions:[]}", "alternativePositions") == []

    def test_objects_in_array_splits_top_level_only(self):
        array = '[{a:1,inner:{b:2}},{a:3}]'
        parts = objects_in_array(array)
        assert len(parts) == 2
        assert scalar(parts[0], "a") == 1
        assert scalar(parts[1], "a") == 3
