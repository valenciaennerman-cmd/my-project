import math
from typing import List
from app.services.sbc.models import CanonicalPlayer

def calculate_team_rating(squad: List[CanonicalPlayer]) -> int:
    """
    Calculates the team rating using the exact EA FC formula.
    Final Rating = (S + sum(max(0, R_i - base_avg))) // 11
    where S is sum of ratings, base_avg is S // 11.
    """
    if not squad:
        return 0

    # We must compute S using only the ratings of players present.
    # But wait, what if the squad has less than 11 players?
    # The divisor in EA FC for rating is always 11.
    # The sum S is the sum of all player ratings in the squad.
    S = sum(p.rating for p in squad)
    base_avg = S // 11

    correction = sum(max(0, p.rating - base_avg) for p in squad)

    return (S + correction) // 11
