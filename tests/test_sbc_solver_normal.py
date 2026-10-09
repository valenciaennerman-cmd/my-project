import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge, Requirement
from app.services.sbc.solver_normal import CPNormalSolver

def test_chem_solver_basic():
    pool = [
        CanonicalPlayer(definition_id="1", name="P1", rating=80, league_id=1, nation_id=1, club_id=1),
        CanonicalPlayer(definition_id="2", name="P2", rating=80, league_id=1, nation_id=1, club_id=1),
        CanonicalPlayer(definition_id="3", name="P3", rating=80, league_id=1, nation_id=1, club_id=1),
        CanonicalPlayer(definition_id="4", name="P4", rating=80, league_id=1, nation_id=2, club_id=2),
    ]
    # To get 3 chem, we need club/nation/league points.
    # P1, P2, P3 have same club (3 players) -> 1 chem for club.
    # They also have same nation (3 players) -> 1 chem for nation.
    # Same league (4 players) -> 1 chem for league.

    challenge = NormalizedChallenge(
        challenge_id="c1",
        name="test",
        required_player_count=3,
        requirements=[Requirement(req_type="MIN_CHEM", val=3, scope="MIN")]
    )

    solver = CPNormalSolver(pool)
    res = solver.solve(challenge)
    assert res is not None
    assert len(res) == 3

def test_league_nation_constraints():
    pool = [
        CanonicalPlayer(definition_id="1", name="P1", rating=80, league_id=1, nation_id=1, club_id=1),
        CanonicalPlayer(definition_id="2", name="P2", rating=80, league_id=2, nation_id=2, club_id=2),
        CanonicalPlayer(definition_id="3", name="P3", rating=80, league_id=3, nation_id=3, club_id=3),
    ]

    challenge = NormalizedChallenge(
        challenge_id="c1",
        name="test",
        required_player_count=2,
        requirements=[
            Requirement(req_type="MIN_LEAGUES", val=2, scope="MIN"),
            Requirement(req_type="SAME_NATION_COUNT", val=1, scope="MAX")
        ]
    )

    solver = CPNormalSolver(pool)
    res = solver.solve(challenge)
    assert res is not None

    leagues = {p.league_id for p in res}
    assert len(leagues) == 2
    nations = [p.nation_id for p in res]
    assert len(set(nations)) == 2

def test_rare_constraint():
    pool = [
        CanonicalPlayer(definition_id="1", name="P1", rating=80, is_rare=True),
        CanonicalPlayer(definition_id="2", name="P2", rating=80, is_rare=False),
    ]
    challenge = NormalizedChallenge(
        challenge_id="c1",
        name="test",
        required_player_count=1,
        requirements=[Requirement(req_type="EXACT_RARE", val=1, scope="EXACT")]
    )
    solver = CPNormalSolver(pool)
    res = solver.solve(challenge)
    assert res is not None
    assert res[0].is_rare == True

def test_empty_pool():
    solver = CPNormalSolver([])
    challenge = NormalizedChallenge(
        challenge_id="empty",
        name="empty",
        required_player_count=11,
        requirements=[]
    )
    assert solver.solve(challenge) is None

def test_unsupported_requirement():
    pool = [CanonicalPlayer(definition_id="1", name="P1", rating=80)]
    challenge = NormalizedChallenge(
        challenge_id="unsup",
        name="unsup",
        required_player_count=1,
        requirements=[Requirement(req_type="MAGIC_REQ", val=1, scope="MIN")]
    )
    solver = CPNormalSolver(pool)
    with pytest.raises(ValueError, match="UNSUPPORTED_REQUIREMENT: MAGIC_REQ"):
        solver.solve(challenge)

def test_infeasible_challenge():
    pool = [CanonicalPlayer(definition_id="1", name="P1", rating=80)]
    challenge = NormalizedChallenge(
        challenge_id="inf",
        name="inf",
        required_player_count=2,
        requirements=[]
    )
    solver = CPNormalSolver(pool)
    assert solver.solve(challenge) is None

def test_totw_constraint():
    pool = [
        CanonicalPlayer(definition_id="1", name="P1", rating=80, is_special=True),
        CanonicalPlayer(definition_id="2", name="P2", rating=80, is_special=False),
    ]
    challenge = NormalizedChallenge(
        challenge_id="totw",
        name="totw",
        required_player_count=1,
        requirements=[Requirement(req_type="MIN_TOTW", val=1, scope="MIN")]
    )
    solver = CPNormalSolver(pool)
    res = solver.solve(challenge)
    assert res is not None
    assert len(res) == 1
    assert res[0].is_special is True
