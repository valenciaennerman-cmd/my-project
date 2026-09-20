"""Candidate matching: which player, then which of that player's cards."""
from __future__ import annotations

from app.models.schemas import CardReading
from app.services.matching.matcher import (
    NAME_SCORE_FLOOR,
    filter_cards,
    match_player,
    rank_by_style,
)

INDEX = {
    "zinedine zidane": (1397, "1397-zinedine-zidane"),
    "kylian mbappe": (231747, "231747-kylian-mbappe"),
    "marina marti serna": (19617, "19617-marina-marti-serna"),
    "kika nazareth": (5001, "5001-kika-nazareth"),
    "robin le normand": (956, "956-robin-le-normand"),
    "lionel messi": (158023, "158023-lionel-messi"),
    "luca zidane": (8174, "8174-luca-zidane"),
}


def reading(**kwargs) -> CardReading:
    base = {"is_card": True, "name": None, "rating": None, "position": None}
    base.update(kwargs)
    return CardReading(**base)


class TestMatchPlayer:
    def test_surname_only_finds_full_name(self):
        """Cards print 'Zidane', the catalog knows 'zinedine zidane'."""
        hits = match_player("Zidane", INDEX)
        assert hits
        assert hits[0].base_player_ea_id in (1397, 8174)
        assert any(h.base_player_ea_id == 1397 for h in hits)

    def test_accented_name_matches_ascii_index(self):
        hits = match_player("Kylian Mbappé", INDEX)
        assert hits[0].base_player_ea_id == 231747

    def test_turkish_and_accent_folding(self):
        hits = match_player("Marina Martí", INDEX)
        assert hits[0].base_player_ea_id == 19617

    def test_glued_name_from_ocr_style_output(self):
        hits = match_player("KikaNazareth", INDEX)
        assert hits[0].base_player_ea_id == 5001
        assert hits[0].score == 100.0

    def test_multi_word_surname(self):
        hits = match_player("Le Normand", INDEX)
        assert hits[0].base_player_ea_id == 956

    def test_nonsense_returns_nothing(self):
        assert match_player("qwertyuiop zxcvb", INDEX) == []

    def test_empty_inputs(self):
        assert match_player("", INDEX) == []
        assert match_player("Zidane", {}) == []

    def test_scores_are_above_the_floor(self):
        for hit in match_player("Messi", INDEX):
            assert hit.score >= NAME_SCORE_FLOOR


class TestFilterCards:
    def test_rating_narrows_the_pool(self, card_factory):
        cards = [
            card_factory(1397, rating=94),
            card_factory(67110261, rating=86, version="Debut International Icon"),
        ]
        out = filter_cards(cards, reading(name="Zidane", rating=86))
        assert [c.ea_id for c in out] == [67110261]

    def test_the_zidane_pair_survives_as_two_candidates(self, card_factory):
        """Name + rating + position cannot separate these -- the user must."""
        cards = [
            card_factory(1397, rating=94, version="Base Icon"),
            card_factory(100664693, rating=94, version="Base Icon Pristine Holographic"),
        ]
        out = filter_cards(cards, reading(name="Zidane", rating=94, position="CAM"))
        assert len(out) == 2

    def test_position_breaks_a_tie_when_it_can(self, card_factory):
        cards = [
            card_factory(1, rating=84, position="ST"),
            card_factory(2, rating=84, position="GK"),
        ]
        out = filter_cards(cards, reading(name="X", rating=84, position="GK"))
        assert [c.ea_id for c in out] == [2]

    def test_alternative_position_counts(self, card_factory):
        cards = [
            card_factory(1, rating=88, position="RB", alt=["RM"]),
            card_factory(2, rating=88, position="CB"),
        ]
        out = filter_cards(cards, reading(name="Maicon", rating=88, position="RM"))
        assert [c.ea_id for c in out] == [1]

    def test_off_by_one_rating_is_tolerated(self, card_factory):
        """A single misread digit should not drop the only real candidate."""
        cards = [card_factory(1, rating=94)]
        out = filter_cards(cards, reading(name="Zidane", rating=93))
        assert [c.ea_id for c in out] == [1]

    def test_far_off_rating_is_not_tolerated(self, card_factory):
        cards = [card_factory(1, rating=94)]
        # RapidOCR read Zidane's 94 as "6"; that must not match.
        assert filter_cards(cards, reading(name="Zidane", rating=6)) == []

    def test_no_rating_keeps_everything(self, card_factory):
        cards = [card_factory(1, rating=94), card_factory(2, rating=86)]
        assert len(filter_cards(cards, reading(name="Zidane"))) == 2


class TestRankByStyle:
    def test_holographic_artwork_ranks_the_holographic_card_first(self, card_factory):
        cards = [
            card_factory(1397, version="Base Icon"),
            card_factory(100664693, version="Base Icon Pristine Holographic"),
        ]
        ranked = rank_by_style(
            cards,
            reading(
                name="Zidane", rating=94, card_type="icon",
                card_style_description="pink iridescent holographic sheen over white marble",
            ),
        )
        assert ranked[0].ea_id == 100664693

    def test_plain_artwork_ranks_the_plain_card_first(self, card_factory):
        cards = [
            card_factory(100664693, version="Base Icon Pristine Holographic"),
            card_factory(1397, version="Base Icon"),
        ]
        ranked = rank_by_style(
            cards,
            reading(name="Zidane", rating=94, card_type="icon",
                    card_style_description="white marble with gold trim"),
        )
        assert ranked[0].ea_id == 1397

    def test_ranking_never_drops_candidates(self, card_factory):
        cards = [card_factory(1), card_factory(2), card_factory(3)]
        ranked = rank_by_style(cards, reading(name="X", card_style_description="gold"))
        assert {c.ea_id for c in ranked} == {1, 2, 3}

    def test_no_style_hint_keeps_order(self, card_factory):
        cards = [card_factory(1), card_factory(2)]
        assert rank_by_style(cards, reading(name="X")) == cards
