import pytest
from app.services.sbc.models import CanonicalPlayer
from app.services.sbc.rating import calculate_team_rating

def make_player(rating):
    return CanonicalPlayer(
        definition_id="1",
        name="Test",
        rating=rating
    )

def test_calculate_team_rating():
    # 11 80s -> 80
    squad = [make_player(80) for _ in range(11)]
    assert calculate_team_rating(squad) == 80

def test_calculate_team_rating_correction():
    # One 90 and ten 80s
    # Sum = 890
    # base_avg = 890 / 11 = 80.909
    # diff = 90 - 80.909 = 9.09
    # Final = (890 + 9.09) / 11 = 81.73 -> 81
    squad = [make_player(80) for _ in range(10)] + [make_player(90)]
    assert calculate_team_rating(squad) == 81

def test_calculate_team_rating_incomplete():
    # If squad has < 11 players, missing count as 0.
    # S = 800, base_avg = 800 // 11 = 72
    # diffs = 10 * (80 - 72) = 80
    # Final = (800 + 80) // 11 = 880 // 11 = 80
    squad = [make_player(80) for _ in range(10)]
    assert calculate_team_rating(squad) == 80

def test_calculate_team_rating_thresholds():
    # Example hitting exact boundary
    # If we want it to be close to the next number but floored down
    squad = [make_player(80) for _ in range(9)] + [make_player(81), make_player(89)]
    # Sum = 9 * 80 + 81 + 89 = 720 + 170 = 890
    # base_avg = 80.909090...
    # max(0, 81 - 80.909) = 0.090909...
    # max(0, 89 - 80.909) = 8.090909...
    # sum max = 8.181818...
    # (890 + 8.181818) / 11 = 898.181818 / 11 = 81.6528 -> 81
    assert calculate_team_rating(squad) == 81

def test_calculate_team_rating_empty():
    assert calculate_team_rating([]) == 0
