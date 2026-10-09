import pytest
from app.services.sbc.models import CanonicalPlayer
from app.services.sbc.chemistry import calculate_chemistry

def create_player(
    definition_id="1",
    league_id=1,
    nation_id=1,
    club_id=1,
    is_icon=False,
    is_hero=False
):
    return CanonicalPlayer(
        definition_id=definition_id,
        name="Test Player",
        rating=80,
        league_id=league_id,
        nation_id=nation_id,
        club_id=club_id,
        is_icon=is_icon,
        is_hero=is_hero
    )

def test_zero_chemistry():
    # 11 completely different players
    squad = [
        create_player(definition_id=str(i), league_id=i, nation_id=i, club_id=i)
        for i in range(11)
    ]
    assert calculate_chemistry(squad) == 0

def test_club_thresholds():
    squad_2 = [create_player(definition_id=str(i), club_id=1, league_id=i, nation_id=i) for i in range(2)]
    assert calculate_chemistry(squad_2) == 2

    squad_3 = [create_player(definition_id=str(i), club_id=1, league_id=i, nation_id=i) for i in range(3)]
    assert calculate_chemistry(squad_3) == 3

    squad_4 = [create_player(definition_id=str(i), club_id=1, league_id=i, nation_id=i) for i in range(4)]
    assert calculate_chemistry(squad_4) == 8

    squad_7 = [create_player(definition_id=str(i), club_id=1, league_id=i, nation_id=i) for i in range(7)]
    assert calculate_chemistry(squad_7) == 21

def test_nation_thresholds():
    squad_2 = [create_player(definition_id=str(i), nation_id=1, club_id=i, league_id=i) for i in range(2)]
    assert calculate_chemistry(squad_2) == 2

    squad_5 = [create_player(definition_id=str(i), nation_id=1, club_id=i, league_id=i) for i in range(5)]
    assert calculate_chemistry(squad_5) == 10

    squad_8 = [create_player(definition_id=str(i), nation_id=1, club_id=i, league_id=i) for i in range(8)]
    assert calculate_chemistry(squad_8) == 24

def test_league_thresholds():
    squad_3 = [create_player(definition_id=str(i), league_id=1, club_id=i, nation_id=i) for i in range(3)]
    assert calculate_chemistry(squad_3) == 3

    squad_5 = [create_player(definition_id=str(i), league_id=1, club_id=i, nation_id=i) for i in range(5)]
    assert calculate_chemistry(squad_5) == 10

    squad_8 = [create_player(definition_id=str(i), league_id=1, club_id=i, nation_id=i) for i in range(8)]
    assert calculate_chemistry(squad_8) == 24

def test_max_chemistry_cap():
    # 8 players same club, league, nation -> should be capped at 3 chem each = 24
    squad = [create_player(definition_id=str(i), league_id=1, club_id=1, nation_id=1) for i in range(8)]
    assert calculate_chemistry(squad) == 24

def test_hero_chemistry():
    # Heroes get 3 chem, give 2 to league, 1 to nation
    squad = [
        create_player(definition_id="1", is_hero=True, league_id=1, nation_id=1, club_id=100),
        create_player(definition_id="2", league_id=1, nation_id=2, club_id=2),
    ]
    assert calculate_chemistry(squad) == 4

def test_icon_chemistry():
    # Icons get 3 chem, give 1 to every league, 2 to nation
    squad = [
        create_player(definition_id="1", is_icon=True, nation_id=1, league_id=99, club_id=99),
        create_player(definition_id="2", league_id=1, nation_id=2, club_id=2),
        create_player(definition_id="3", league_id=1, nation_id=3, club_id=3),
    ]
    # Icon gets 3, players get 1 each from league since icon adds 1 to league 1
    assert calculate_chemistry(squad) == 5

    squad2 = [
        create_player(definition_id="1", is_icon=True, nation_id=1, league_id=99, club_id=99),
        create_player(definition_id="2", league_id=1, nation_id=1, club_id=2),
        create_player(definition_id="3", league_id=2, nation_id=1, club_id=3),
    ]
    # Icon gives 2 to nation 1. p2 and p3 give 1 each. Total nation 1 = 4.
    # Nation chem for 4 is 1 (needs 5 for 2).
    # p2 league=1 count = 1(p2) + 1(icon) = 2 (needs 3 for chem).
    # p3 league=2 count = 1(p3) + 1(icon) = 2 (needs 3 for chem).
    # So p2 gets 1 chem (nation), p3 gets 1 chem (nation).
    # Total = 3 (icon) + 1 + 1 = 5.
    assert calculate_chemistry(squad2) == 5

def test_multiple_icons_and_heroes():
    squad = [
        create_player(definition_id="1", is_icon=True, nation_id=1),
        create_player(definition_id="2", is_icon=True, nation_id=2),
        create_player(definition_id="3", is_hero=True, league_id=1, nation_id=1),
        create_player(definition_id="4", league_id=1, nation_id=3, club_id=3),
    ]
    # icon1 gets 3
    # icon2 gets 3
    # hero gets 3
    # p4:
    # league_id 1: 2 (from hero) + 1 (p4) = 3. Plus 2 icons = 5.
    # So p4 gets 2 chem from league!
    # Total = 3 + 3 + 3 + 2 = 11.
    assert calculate_chemistry(squad) == 11
def test_fc27_rules_remain_unverified():
    from app.services.sbc.chemistry import chemistry_rules_fc27, get_rules_confidence
    assert chemistry_rules_fc27["authoritative"] is False
    assert get_rules_confidence(chemistry_rules_fc27).startswith("UNVERIFIED_DOMAIN_RULE")
