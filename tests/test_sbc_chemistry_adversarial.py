import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge, Requirement
from app.services.sbc.chemistry import calculate_chemistry
from app.services.sbc.solver_normal import CPNormalSolver

def test_icon_league_chemistry_adversarial():
    # An icon that somehow has a league ID (e.g. "Icons" league)
    # This shouldn't double-count in CP-SAT or chemistry.py
    icon = CanonicalPlayer(
        definition_id="1", name="Pele", rating=95, is_icon=True,
        league_id=2118, nation_id=54, club_id=112658
    )
    # A normal player in a completely different league
    normal1 = CanonicalPlayer(
        definition_id="2", name="Normal 1", rating=80,
        league_id=13, nation_id=54, club_id=1
    )
    # A normal player in the same league as the icon's league_id
    normal2 = CanonicalPlayer(
        definition_id="3", name="Normal 2", rating=80,
        league_id=2118, nation_id=1, club_id=2
    )

    squad = [icon, normal1, normal2]

    # Calculate chemistry.py output
    chem = calculate_chemistry(squad)

    # Test CP-SAT output
    # Just setting MIN_CHEM = 1, required = 3
    challenge = NormalizedChallenge(
        challenge_id="c1", name="Test", required_player_count=3,
        requirements=[Requirement(req_type="MIN_CHEM", val=1, scope="MIN")]
    )

    solver = CPNormalSolver(pool=squad)
    res = solver.solve(challenge)

    assert res is not None, "Solver should find a valid squad"

    challenge_exact = NormalizedChallenge(
        challenge_id="c2", name="Test", required_player_count=3,
        requirements=[Requirement(req_type="MIN_CHEM", val=chem, scope="MIN")]
    )
    res_exact = solver.solve(challenge_exact)
    assert res_exact is not None, f"Solver should satisfy min chem {chem}"

    challenge_over = NormalizedChallenge(
        challenge_id="c3", name="Test", required_player_count=3,
        requirements=[Requirement(req_type="MIN_CHEM", val=chem+1, scope="MIN")]
    )
    res_over = solver.solve(challenge_over)
    assert res_over is None, f"Solver should FAIL at min chem {chem+1}, meaning CP-SAT calculates exactly {chem}"

def test_hero_chemistry():
    hero = CanonicalPlayer(
        definition_id="4", name="Hero", rating=89, is_hero=True,
        league_id=13, nation_id=54, club_id=10
    )
    normal = CanonicalPlayer(
        definition_id="5", name="Normal", rating=80,
        league_id=13, nation_id=1, club_id=1
    )
    squad = [hero, normal]
    chem = calculate_chemistry(squad)

    challenge = NormalizedChallenge(
        challenge_id="h1", name="Test", required_player_count=2,
        requirements=[Requirement(req_type="MIN_CHEM", val=chem, scope="MIN")]
    )
    solver = CPNormalSolver(pool=squad)
    assert solver.solve(challenge) is not None

    challenge_over = NormalizedChallenge(
        challenge_id="h2", name="Test", required_player_count=2,
        requirements=[Requirement(req_type="MIN_CHEM", val=chem+1, scope="MIN")]
    )
    assert solver.solve(challenge_over) is None
