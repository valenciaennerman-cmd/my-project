import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge
from app.services.sbc.solver_streamlined import CPStreamlinedSolver

def create_player(definition_id, item_score, market_price, locked=False, excluded=False):
    return CanonicalPlayer(
        definition_id=definition_id,
        name=f"Player_{definition_id}",
        rating=item_score, # just to satisfy model
        item_score=item_score,
        market_price=market_price,
        locked=locked,
        excluded=excluded,
        tradeable=True
    )

def test_streamlined_solver_overshoot():
    # Test that solver prioritizes minimizing cost first, then minimizing overshoot
    pool = [
        create_player("1", item_score=10, market_price=100),
        create_player("2", item_score=15, market_price=100),
        create_player("3", item_score=20, market_price=1000),
    ]

    challenge = NormalizedChallenge(challenge_id="1", name="C", required_player_count=11, score_requirement=20)
    solver = CPStreamlinedSolver(pool)
    solution = solver.solve(challenge)

    assert solution is not None
    assert len(solution) == 2
    ids = {p.definition_id for p in solution}
    assert ids == {"1", "2"}

    # Now let's test overshoot priority.
    pool2 = [
        create_player("1", item_score=20, market_price=500),
        create_player("2", item_score=25, market_price=500),
    ]
    solver2 = CPStreamlinedSolver(pool2)
    solution2 = solver2.solve(challenge)

    assert solution2 is not None
    assert len(solution2) == 1
    assert solution2[0].definition_id == "1"

    # Test dynamic multiplier failure
    # P1 cost 100, score 2000 (overshoot 0)
    # P2 cost 99, score 3500 (overshoot 1500)
    # Cost is primary! So it MUST pick P2 because 99 < 100.
    # If the multiplier is 1000:
    # P1: 100*1000 + 2000 = 102000
    # P2: 99*1000 + 3500 = 102500 -> It will incorrectly pick P1.
    pool3 = [
        create_player("1", item_score=2000, market_price=100),
        create_player("2", item_score=3500, market_price=99),
    ]
    challenge3 = NormalizedChallenge(challenge_id="3", name="C3", required_player_count=11, score_requirement=2000)
    solver3 = CPStreamlinedSolver(pool3)
    solution3 = solver3.solve(challenge3)

    assert solution3 is not None
    assert len(solution3) == 1
    assert solution3[0].definition_id == "2" # MUST pick the one with lower cost

def test_streamlined_solver_locked_excluded():
    pool = [
        create_player("1", item_score=10, market_price=100),
        create_player("2", item_score=10, market_price=100),
        create_player("3", item_score=10, market_price=100, excluded=True),
        create_player("4", item_score=10, market_price=5000, locked=True), # Expensive but locked
    ]

    challenge = NormalizedChallenge(challenge_id="1", name="C", required_player_count=11, score_requirement=20)
    solver = CPStreamlinedSolver(pool)
    solution = solver.solve(challenge)

    assert solution is not None
    ids = {p.definition_id for p in solution}

    # Target is 20.
    # P4 is locked, so it MUST be included (score 10).
    # We need 10 more score.
    # P1 and P2 provide 10 score for 100 price.
    # P3 provides 10 score for 100 price, but is excluded.
    # So it should pick P4 + P1 (or P2).
    assert "4" in ids
    assert "3" not in ids
    assert len(ids) == 2
