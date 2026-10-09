import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge
from app.services.sbc.solver_streamlined import CPStreamlinedSolver, SOLVER_SAFETY_MAX_ITEMS

def test_streamlined_limit():
    pool = [CanonicalPlayer(definition_id=str(i), name=str(i), rating=80, market_price=100, item_score=1) for i in range(200)]

    # 1. Default challenge (required_player_count = 11) should use 150 (SOLVER_SAFETY_MAX_ITEMS)
    challenge_default = NormalizedChallenge(
        challenge_id="test", name="test", required_player_count=11, score_requirement=0
    )
    solver = CPStreamlinedSolver(pool)
    result_default = solver.solve(challenge_default, points_to_submit=100)
    assert len(result_default) <= SOLVER_SAFETY_MAX_ITEMS

    # 2. Challenge with specific max_player_count < 150
    challenge_small = NormalizedChallenge(
        challenge_id="test2", name="test2", required_player_count=50, score_requirement=0
    )
    result_small = solver.solve(challenge_small, points_to_submit=50)
    assert len(result_small) <= 50

def test_protect_expensive():
    # Test that setting protect_expensive = True excludes players > 50000
    p = CanonicalPlayer(definition_id="1", name="expensive", rating=90, market_price=60000, excluded=True)
    assert p.effective_cost > 1000000 # Since excluded

def test_prefer_untradeable():
    # Test prefer_untradeable alters effective cost
    p_tradeable = CanonicalPlayer(definition_id="2", name="t", rating=85, market_price=10000, tradeable=True)

    p_untradeable_prefer = CanonicalPlayer(definition_id="3", name="u_pref", rating=85, market_price=10000, tradeable=False, prefer_untradeable=True)

    p_untradeable_noprefer = CanonicalPlayer(definition_id="4", name="u_nopref", rating=85, market_price=10000, tradeable=False, prefer_untradeable=False)

    assert p_tradeable.effective_cost == 10000
    assert p_untradeable_prefer.effective_cost == 1000 # 10%
    assert p_untradeable_noprefer.effective_cost == 10000 # 100%

def test_solver_uses_effective_cost():
    # The solver should pick the untradeable player if prefer_untradeable is True
    p1 = CanonicalPlayer(definition_id="1", name="t", rating=85, market_price=10000, tradeable=True, item_score=10)
    p2 = CanonicalPlayer(definition_id="2", name="u", rating=85, market_price=10000, tradeable=False, prefer_untradeable=True, item_score=10)
    pool = [p1, p2]

    challenge = NormalizedChallenge(challenge_id="test", name="test", required_player_count=1)
    solver = CPStreamlinedSolver(pool)
    result = solver.solve(challenge, points_to_submit=10)

    assert len(result) == 1
    assert result[0].definition_id == "2"
