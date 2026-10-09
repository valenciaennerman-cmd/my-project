import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge, Requirement
from app.services.sbc.solver_normal import CPNormalSolver
from app.services.sbc.verifier import IndependentVerifier

@pytest.fixture
def identity_pool():
    return [
        CanonicalPlayer(
            definition_id="def_100",
            instance_id="inst_1",
            name="Test Player Same 1",
            rating=80,
            league_id=13,
            nation_id=14,
            club_id=15,
            is_rare=True
        ),
        CanonicalPlayer(
            definition_id="def_100",
            instance_id="inst_2",
            name="Test Player Same 2",
            rating=80,
            league_id=13,
            nation_id=14,
            club_id=15,
            is_rare=True
        ),
        CanonicalPlayer(
            definition_id="def_100",
            instance_id="inst_3",
            name="Test Player Same 3",
            rating=80,
            league_id=13,
            nation_id=14,
            club_id=15,
            is_rare=True
        )
    ]

def test_sbc_identity_same_definition(identity_pool):
    challenge = NormalizedChallenge(
        challenge_id="chal_ident_1",
        name="Identity Test",
        required_player_count=3,
        requirements=[
            Requirement(req_type="MIN_CHEM", val=0, scope="MIN")
        ]
    )

    solver = CPNormalSolver(identity_pool)
    solution = solver.solve(challenge)

    assert solution is not None, "Solver should allow multiple instances of the same definition_id"
    assert len(solution) == 3

    instances = {p.instance_id for p in solution}
    assert len(instances) == 3, "All three unique instances should be selected"

    # Test verifier
    verification = IndependentVerifier.verify_normal_squad(solution, challenge, inventory=identity_pool)
    assert verification["valid"] is True, f"Verifier should pass same definition_id: {verification['errors']}"

def test_sbc_identity_duplicate_instance_fails(identity_pool):
    challenge = NormalizedChallenge(
        challenge_id="chal_ident_2",
        name="Identity Test Dup",
        required_player_count=3,
        requirements=[]
    )
    # create invalid squad with duplicate instance
    squad = [identity_pool[0], identity_pool[0], identity_pool[1]]

    verification = IndependentVerifier.verify_normal_squad(squad, challenge, inventory=identity_pool)
    assert verification["valid"] is False
    assert any("Duplicate instances" in e for e in verification["errors"])


def test_repeated_definition_without_physical_ids_is_ambiguous():
    pool = [CanonicalPlayer(definition_id="100", name="A", rating=80),
            CanonicalPlayer(definition_id="100", name="B", rating=80)]
    challenge = NormalizedChallenge(challenge_id="ambiguous", name="Ambiguous", required_player_count=2)
    assert CPNormalSolver(pool).solve_with_status(challenge).status.value == "INFEASIBLE"
    result = IndependentVerifier.verify_normal_squad(pool, challenge)
    assert result["valid"] is False
