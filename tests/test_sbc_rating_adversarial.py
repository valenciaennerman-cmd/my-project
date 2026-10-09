import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge, Requirement
from app.services.sbc.rating import calculate_team_rating
from app.services.sbc.solver_normal import CPNormalSolver

def make_player(idx, rating):
    return CanonicalPlayer(
        definition_id=str(idx),
        name=f"Player_{idx}",
        rating=rating,
        preferred_position="ST",
        club_id=1,
        league_id=1,
        nation_id=1,
        is_rare=False,
        is_special=False,
        is_icon=False,
        is_hero=False,
        market_price=1000,
        tradeable=False
    )

def test_sbc_rating_adversarial_exact_thresholds():
    # 2x 87, 9x 84 -> Should be exactly 85, NOT 84
    ratings = [87, 87] + [84] * 9
    squad = [make_player(i, r) for i, r in enumerate(ratings)]

    rating = calculate_team_rating(squad)
    assert rating == 85, f"Expected 85, got {rating}"

def test_sbc_rating_adversarial_one_point_below():
    # 9x 84, 2x 83 -> Should be exactly 84, NOT 83
    ratings = [84] * 9 + [83] * 2
    squad = [make_player(i, r) for i, r in enumerate(ratings)]

    rating = calculate_team_rating(squad)
    assert rating == 84, f"Expected 84, got {rating}"

def test_sbc_rating_adversarial_10_items():
    # What if only 10 items?
    # Say we need 85 rating from 10 items.
    # 930 is the sum. 10x 93 -> Sum 930. Avg 930 // 11 = 84.
    # Excess: 10 * (93 - 84) = 90.
    # Rating = (930 + 90) // 11 = 1020 // 11 = 92
    ratings = [93] * 10
    squad = [make_player(i, r) for i, r in enumerate(ratings)]

    rating = calculate_team_rating(squad)
    assert rating == 92, f"Expected 92, got {rating}"

def test_sbc_solver_uses_correct_formula():
    pool = [make_player(i, r) for i, r in enumerate([87, 87] + [84]*9)]
    challenge = NormalizedChallenge(
        challenge_id="test",
        name="Test Challenge",
        required_player_count=11,
        requirements=[Requirement(req_type="TEAM_RATING", scope="MIN", val=85)]
    )

    solver = CPNormalSolver(pool)
    solution = solver.solve(challenge, max_time_seconds=2.0)

    # Under old logic (float), this pool can only reach 84.
    # It should reach 85 and return a solution.
    assert solution is not None, "Solver failed to find a valid 85-rated squad"
    assert len(solution) == 11
