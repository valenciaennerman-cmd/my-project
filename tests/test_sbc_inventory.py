import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge, Requirement
from app.services.sbc.verifier import IndependentVerifier
from app.services.sbc.solver_normal import CPNormalSolver

def test_inventory_unique_instance_id_verifier():
    # Two players with same instance_id
    p1 = CanonicalPlayer(definition_id="100", instance_id="instance_A", name="Mbappe", rating=90)
    p2 = CanonicalPlayer(definition_id="101", instance_id="instance_A", name="Mbappe 2", rating=90)
    squad = [p1, p2] + [CanonicalPlayer(definition_id=str(i), instance_id=f"inst_{i}", name="P", rating=80) for i in range(2, 11)]

    challenge = NormalizedChallenge(
        challenge_id="c1",
        name="Test",
        required_player_count=11,
        requirements=[]
    )

    result = IndependentVerifier.verify_normal_squad(squad, challenge)
    assert result["valid"] is False
    assert any("Duplicate instances" in e for e in result["errors"])

def test_inventory_unique_definition_id_verifier():
    p1 = CanonicalPlayer(definition_id="100", instance_id="inst_100_A", name="Mbappe", rating=90)
    p2 = CanonicalPlayer(definition_id="100", instance_id="inst_100_B", name="Mbappe", rating=90)
    squad = [p1, p2] + [CanonicalPlayer(definition_id=str(i), instance_id=f"inst_{i}", name="P", rating=80) for i in range(2, 11)]

    challenge = NormalizedChallenge(
        challenge_id="c2",
        name="Test",
        required_player_count=11,
        requirements=[]
    )

    result = IndependentVerifier.verify_normal_squad(squad, challenge)
    assert result["valid"] is True, f"Squad with duplicate definition_ids but unique instance_ids should be valid. Errors: {result.get('errors')}"

def test_inventory_solver_rejects_duplicate_definition_and_instance():
    p1 = CanonicalPlayer(definition_id="100", instance_id="inst_1", name="Mbappe", rating=90)
    p2 = CanonicalPlayer(definition_id="100", instance_id="inst_2", name="Mbappe", rating=90) # same def, diff inst
    p3 = CanonicalPlayer(definition_id="101", instance_id="inst_3", name="Messi", rating=90)
    p4 = CanonicalPlayer(definition_id="102", instance_id="inst_3", name="Duplicate Inst Messi", rating=90) # same inst, diff def

    pool = [p1, p2, p3, p4] + [CanonicalPlayer(definition_id=str(i), instance_id=f"inst_pool_{i}", name="P", rating=80) for i in range(10, 25)]

    challenge = NormalizedChallenge(
        challenge_id="c3",
        name="Test",
        required_player_count=11,
        requirements=[]
    )

    solver = CPNormalSolver(pool)
    solution = solver.solve(challenge)

    assert solution is not None
    # We removed definition_id constraints, so it CAN contain both p1 and p2!
    # But it must not contain both p3 and p4 (same instance_id)

    # Check that solution does not contain both p3 and p4
    inst_ids = [p.instance_id for p in solution if p.instance_id]
    assert len(set(inst_ids)) == len(inst_ids), "Solver selected duplicate instance IDs"
