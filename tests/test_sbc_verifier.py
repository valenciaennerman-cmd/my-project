import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge, Requirement
from app.services.sbc.verifier import IndependentVerifier

def create_player(definition_id, rating, league_id=1, nation_id=1, club_id=1, is_rare=False, is_special=False, instance_id=None):
    return CanonicalPlayer(
        definition_id=str(definition_id),
        instance_id=str(instance_id) if instance_id else f"inst_{definition_id}",
        name=f"Player {definition_id}",
        rating=rating,
        league_id=league_id,
        nation_id=nation_id,
        club_id=club_id,
        is_rare=is_rare,
        is_special=is_special
    )

def test_verifier_short_by_one_rating():
    # 11 players of rating 80 -> avg 80.
    # Target: 81
    squad = [create_player(i, 80) for i in range(11)]
    challenge = NormalizedChallenge(
        challenge_id="c1",
        name="Test",
        required_player_count=11,
        requirements=[Requirement(req_type="TEAM_RATING", val=81, scope="MIN")]
    )
    result = IndependentVerifier.verify_normal_squad(squad, challenge)
    assert result["valid"] is False
    assert any("Rating" in e and "fails MIN" in e for e in result["errors"])

def test_verifier_short_by_one_chemistry():
    # Target: 10 chem. We'll give 3 players from same club/nation/league -> 3*3=9 chem.
    # The rest different so they get 0 chem.
    squad = [create_player(i, 80, league_id=i, nation_id=i, club_id=i) for i in range(11)]
    # Make first 3 same league/nation/club
    squad[0].league_id = 99
    squad[0].nation_id = 99
    squad[0].club_id = 99
    squad[1].league_id = 99
    squad[1].nation_id = 99
    squad[1].club_id = 99
    squad[2].league_id = 99
    squad[2].nation_id = 99
    squad[2].club_id = 99

    # Chem will be:
    # 3 players from same club -> 1 chem each
    # 3 players from same nation -> 1 chem each
    # 3 players from same league -> 1 chem each
    # Total for each = 3. Total for squad = 9.

    challenge = NormalizedChallenge(
        challenge_id="c2",
        name="Test Chem",
        required_player_count=11,
        requirements=[Requirement(req_type="MIN_CHEM", val=10, scope="MIN")]
    )
    result = IndependentVerifier.verify_normal_squad(squad, challenge)
    assert result["valid"] is False
    assert any("Chemistry" in e for e in result["errors"])

def test_verifier_duplicate_instances():
    # Duplicate instance_id!
    squad = [create_player(1, 80, instance_id="dup")] * 2 + [create_player(i, 80) for i in range(2, 11)]
    challenge = NormalizedChallenge(
        challenge_id="c3",
        name="Test Duplicate",
        required_player_count=11,
        requirements=[]
    )
    result = IndependentVerifier.verify_normal_squad(squad, challenge)
    assert result["valid"] is False
    assert any("Duplicate instances" in e for e in result["errors"])

def test_verifier_violate_league_constraint():
    # Require MAX 2 players from same league
    squad = [create_player(i, 80, league_id=1) for i in range(3)] + [create_player(i, 80, league_id=i) for i in range(3, 11)]
    challenge = NormalizedChallenge(
        challenge_id="c4",
        name="Test League",
        required_player_count=11,
        requirements=[Requirement(req_type="SAME_LEAGUE_COUNT", val=2, scope="MAX")]
    )
    result = IndependentVerifier.verify_normal_squad(squad, challenge)
    assert result["valid"] is False
    assert any("Max same league" in e for e in result["errors"])

def test_verifier_streamlined_constraints():
    squad = [create_player(1, 80, is_rare=True), create_player(2, 80, is_rare=True)]
    challenge = NormalizedChallenge(
        challenge_id="c5",
        name="Streamlined",
        type="STREAMLINED",
        required_player_count=2,
        requirements=[
            Requirement(req_type="RARITY", val=3, scope="MIN")
        ],
        score_requirement=100
    )
    # Target score 100
    squad[0].item_score = 40
    squad[1].item_score = 40 # Total 80 < 100
    result = IndependentVerifier.verify_streamlined_squad(squad, challenge, 100)
    assert result["valid"] is False
    assert any("Score" in e for e in result["errors"])
    assert any("Rare cards" in e for e in result["errors"])

def test_verifier_valid_normal_squad():
    squad = [create_player(i, 80) for i in range(11)]
    challenge = NormalizedChallenge(
        challenge_id="c1",
        name="Test",
        required_player_count=11,
        requirements=[Requirement(req_type="TEAM_RATING", val=80, scope="MIN")]
    )
    result = IndependentVerifier.verify_normal_squad(squad, challenge)
    assert result["valid"] is True
    assert len(result["errors"]) == 0

def test_verifier_valid_streamlined_squad():
    squad = [create_player(1, 80, is_rare=True), create_player(2, 80, is_rare=True)]
    squad[0].item_score = 50
    squad[1].item_score = 50
    challenge = NormalizedChallenge(
        challenge_id="c2",
        name="Streamlined",
        type="STREAMLINED",
        required_player_count=2,
        requirements=[
            Requirement(req_type="RARITY", val=2, scope="MIN")
        ],
        score_requirement=100
    )
    result = IndependentVerifier.verify_streamlined_squad(squad, challenge, 100)
    assert result["valid"] is True
    assert len(result["errors"]) == 0
