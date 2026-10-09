import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge, Requirement
from app.services.sbc.solver_normal import CPNormalSolver

def test_unknown_requirement_raises_error():
    pool = [
        CanonicalPlayer(definition_id="1", name="Player 1", rating=80, is_rare=True, is_special=False, is_icon=False, is_hero=False, club_id=1, nation_id=1, league_id=1, market_price=500),
        CanonicalPlayer(definition_id="2", name="Player 2", rating=80, is_rare=True, is_special=False, is_icon=False, is_hero=False, club_id=1, nation_id=1, league_id=1, market_price=500)
    ]
    solver = CPNormalSolver(pool=pool)

    challenge = NormalizedChallenge(
        challenge_id="ch_1",
        name="Unknown Req Test",
        required_player_count=2,
        requirements=[
            Requirement(req_type="UNKNOWN_WEIRD_REQ", scope="MIN", val=1)
        ]
    )

    with pytest.raises(ValueError, match="UNSUPPORTED_REQUIREMENT"):
        solver.solve(challenge)
