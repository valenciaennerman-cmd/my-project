import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge, Requirement
from app.services.sbc.verifier import IndependentVerifier

def create_player(definition_id, rating, league_id=1, nation_id=1, club_id=1, is_rare=False, is_special=False):
    return CanonicalPlayer(
        definition_id=str(definition_id),
        instance_id=f"inst_{definition_id}",
        name=f"Player {definition_id}",
        rating=rating,
        league_id=league_id,
        nation_id=nation_id,
        club_id=club_id,
        is_rare=is_rare,
        is_special=is_special
    )

def test_verifier_catches_stale_inventory():
    squad = [create_player(i, 80) for i in range(11)]
    # Inventory only has 10 of these players
    inventory = [create_player(i, 80) for i in range(10)]
    challenge = NormalizedChallenge(
        challenge_id="c1",
        name="Test",
        required_player_count=11,
        requirements=[Requirement(req_type="TEAM_RATING", val=80, scope="MIN")]
    )
    result = IndependentVerifier.verify_normal_squad(squad, challenge, inventory=inventory)
    assert result["valid"] is False
    assert any("Inventory" in e or "Stale" in e or "not in inventory" in e for e in result["errors"])

def test_verifier_catches_wrong_ids():
    squad = [create_player(i, 80) for i in range(11)]
    # Inventory has different ids
    inventory = [create_player(i+100, 80) for i in range(11)]
    challenge = NormalizedChallenge(
        challenge_id="c1",
        name="Test",
        required_player_count=11,
        requirements=[Requirement(req_type="TEAM_RATING", val=80, scope="MIN")]
    )
    result = IndependentVerifier.verify_normal_squad(squad, challenge, inventory=inventory)
    assert result["valid"] is False
    assert any("not in inventory" in e for e in result["errors"])

def test_verifier_catches_missing_constraints():
    # If the solver missed a constraint (e.g. required 2 leagues but squad has 1), verifier must catch it.
    squad = [create_player(i, 80, league_id=1) for i in range(11)]
    inventory = [create_player(i, 80, league_id=1) for i in range(11)]
    challenge = NormalizedChallenge(
        challenge_id="c1",
        name="Test",
        required_player_count=11,
        requirements=[Requirement(req_type="LEAGUE_COUNT", val=2, scope="MIN")]
    )
    result = IndependentVerifier.verify_normal_squad(squad, challenge, inventory=inventory)
    assert result["valid"] is False
    assert any("League count" in e for e in result["errors"])

def test_verifier_catches_solver_hallucinated_attributes():
    # 11 true inventory players (rating 80, league 1)
    inventory = [create_player(i, 80, league_id=1) for i in range(11)]

    # Solver maliciously alters rating to 99 and league to 2 to pass requirements
    squad = [create_player(i, 99, league_id=2) for i in range(11)]

    challenge = NormalizedChallenge(
        challenge_id="c1",
        name="Test",
        required_player_count=11,
        requirements=[
            Requirement(req_type="TEAM_RATING", val=90, scope="MIN"),
            Requirement(req_type="LEAGUE_COUNT", val=2, scope="MIN")
        ]
    )
    result = IndependentVerifier.verify_normal_squad(squad, challenge, inventory=inventory)
    assert result["valid"] is False
    assert any("Rating" in e for e in result["errors"])
    assert any("League count" in e for e in result["errors"])
