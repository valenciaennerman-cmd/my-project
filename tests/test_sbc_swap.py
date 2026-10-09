import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge, Requirement
from app.services.sbc.swap import SwapEngine

def test_swap_same_rating_valid_without_repair():
    p1 = CanonicalPlayer(definition_id="1", name="Player 1", rating=80)
    p2 = CanonicalPlayer(definition_id="2", name="Player 2", rating=80)
    p3 = CanonicalPlayer(definition_id="3", name="Player 3", rating=80)

    candidate = CanonicalPlayer(definition_id="4", name="Candidate", rating=80)

    squad = [p1, p2, p3]
    pool = [p1, p2, p3, candidate]

    challenge = NormalizedChallenge(
        challenge_id="c1",
        name="Test",
        required_player_count=3,
        requirements=[]
    )

    # Swap p1 with candidate (both 80 rated)
    new_squad = SwapEngine.attempt_swap(squad, p1, candidate, challenge, pool)
    assert new_squad is not None
    assert len(new_squad) == 3

    definition_ids = [p.definition_id for p in new_squad]
    assert "4" in definition_ids
    assert "1" not in definition_ids
    assert "2" in definition_ids
    assert "3" in definition_ids

def test_swap_different_rating_rejected():
    p1 = CanonicalPlayer(definition_id="1", name="Player 1", rating=80)
    p2 = CanonicalPlayer(definition_id="2", name="Player 2", rating=80)

    candidate = CanonicalPlayer(definition_id="4", name="Candidate", rating=81) # Different rating

    squad = [p1, p2]
    pool = [p1, p2, candidate]

    challenge = NormalizedChallenge(
        challenge_id="c2",
        name="Test",
        required_player_count=2,
        requirements=[]
    )

    # Should reject because 81 != 80
    new_squad = SwapEngine.attempt_swap(squad, p1, candidate, challenge, pool)
    assert new_squad is None

def test_swap_with_repair_needed():
    # Initial squad has a TOTW, rating 80.
    # Swap engine swaps the TOTW with a non-TOTW of same rating.
    # Result invalid due to MIN_TOTW.
    # Repair engine must replace another player with a TOTW from the pool to fix it.

    p1 = CanonicalPlayer(definition_id="1", name="Player 1", rating=80, is_special=True) # The TOTW
    p2 = CanonicalPlayer(definition_id="2", name="Player 2", rating=80, is_special=False)

    candidate = CanonicalPlayer(definition_id="3", name="Candidate", rating=80, is_special=False) # Not TOTW

    # The pool has another TOTW that can be used for repair
    p_repair = CanonicalPlayer(definition_id="4", name="Repair", rating=80, is_special=True)

    squad = [p1, p2]
    pool = [p1, p2, candidate, p_repair]

    challenge = NormalizedChallenge(
        challenge_id="c3",
        name="Test",
        required_player_count=2,
        requirements=[
            Requirement(req_type="MIN_TOTW", val=1, scope="MIN")
        ]
    )

    new_squad = SwapEngine.attempt_swap(squad, p1, candidate, challenge, pool)
    assert new_squad is not None

    definition_ids = [p.definition_id for p in new_squad]
    assert "3" in definition_ids # Candidate was kept
    assert "4" in definition_ids # p_repair was added
    assert "1" not in definition_ids # p1 was swapped out
    assert "2" not in definition_ids # p2 was dropped to make room for p_repair

def test_swap_repair_fails():
    p1 = CanonicalPlayer(definition_id="1", name="Player 1", rating=80, is_special=True) # The TOTW
    p2 = CanonicalPlayer(definition_id="2", name="Player 2", rating=80, is_special=False)
    candidate = CanonicalPlayer(definition_id="3", name="Candidate", rating=80, is_special=False)

    # Pool has NO other TOTW.
    pool = [p1, p2, candidate]

    squad = [p1, p2]
    challenge = NormalizedChallenge(
        challenge_id="c3",
        name="Test",
        required_player_count=2,
        requirements=[
            Requirement(req_type="MIN_TOTW", val=1, scope="MIN")
        ]
    )

    # attempt_swap drops p1 (TOTW) for candidate. Repair fails because no TOTW in pool.
    new_squad = SwapEngine.attempt_swap(squad, p1, candidate, challenge, pool)
    assert new_squad is None
