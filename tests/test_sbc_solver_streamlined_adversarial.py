import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge
from app.services.sbc.solver_streamlined import CPStreamlinedSolver

def create_player(definition_id, rating, item_score, market_price, locked=False, excluded=False):
    return CanonicalPlayer(
        definition_id=definition_id,
        name=f"Player_{definition_id}",
        rating=rating,
        item_score=item_score,
        market_price=market_price,
        locked=locked,
        excluded=excluded,
        tradeable=True
    )

def test_same_ovr_different_score():
    # Two players with same OVR but different item_score (e.g. green gem score).
    # The solver should prioritize the one that fulfills the requirement cheaper or at all,
    # completely ignoring OVR.
    pool = [
        create_player("1", rating=88, item_score=2000, market_price=5000),
        create_player("2", rating=88, item_score=100, market_price=1000),
    ]

    challenge = NormalizedChallenge(
        challenge_id="adv1",
        name="Adv 1",
        required_player_count=11,
        score_requirement=2000
    )

    solver = CPStreamlinedSolver(pool)
    solution = solver.solve(challenge)

    assert solution is not None
    assert len(solution) == 1
    assert solution[0].definition_id == "1"

def test_lexicographic_tie_breaks():
    # If two combinations have the EXACT SAME COST, it should pick the one with the SMALLER overshoot (smaller total item_score).
    pool = [
        create_player("1", rating=80, item_score=1000, market_price=1000),
        create_player("2", rating=80, item_score=1500, market_price=1000),
    ]

    challenge = NormalizedChallenge(
        challenge_id="adv2",
        name="Adv 2",
        required_player_count=11,
        score_requirement=1000
    )

    solver = CPStreamlinedSolver(pool)
    solution = solver.solve(challenge)

    assert solution is not None
    assert len(solution) == 1
    # Both cost 1000, but player 1 has score 1000 (overshoot 0) and player 2 has score 1500 (overshoot 500)
    # The objective minimizes total_cost * multiplier + total_score, so it prefers smaller total_score.
    assert solution[0].definition_id == "1"

def test_not_traditional_11_player_squad():
    # Streamlined SBCs shouldn't require exactly 11 players.
    # If required_player_count isn't strict 11, we could just submit 1 or 50 players.
    pool = [create_player(str(i), rating=70, item_score=100, market_price=100) for i in range(20)]

    # We need 1500 score, which takes 15 players.
    challenge = NormalizedChallenge(
        challenge_id="adv3",
        name="Adv 3",
        required_player_count=11,
        score_requirement=1500
    )

    solver = CPStreamlinedSolver(pool)
    solution = solver.solve(challenge)

    assert solution is not None
    assert len(solution) == 15

def test_dynamic_multiplier_overshoot_edge_case():
    # Large item_scores to ensure the multiplier doesn't overflow or improperly weigh score over cost.
    pool = [
        create_player("1", rating=99, item_score=1000000, market_price=100),
        create_player("2", rating=99, item_score=2000000, market_price=99),
    ]

    challenge = NormalizedChallenge(
        challenge_id="adv4",
        name="Adv 4",
        required_player_count=11,
        score_requirement=1000000
    )

    solver = CPStreamlinedSolver(pool)
    solution = solver.solve(challenge)

    assert solution is not None
    assert len(solution) == 1
    # Player 2 costs 99 (less than 100), but has massive overshoot (1M extra score).
    # Since cost is primary, it must pick Player 2.
    assert solution[0].definition_id == "2"
