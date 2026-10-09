import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge
from app.services.sbc.multi_completion import MultiCompletionEngine
from app.services.sbc.models import Requirement
from app.services.sbc.solver_normal import CPNormalSolver

def test_heuristic_fails_exact_succeeds():
    pool = [
        CanonicalPlayer(definition_id="X1", name="X1", rating=80, item_score=90, market_price=1, tradeable=True),
        CanonicalPlayer(definition_id="X2", name="X2", rating=80, item_score=90, market_price=1, tradeable=True),
        CanonicalPlayer(definition_id="X3", name="X3", rating=80, item_score=90, market_price=1, tradeable=True),
        CanonicalPlayer(definition_id="X4", name="X4", rating=80, item_score=90, market_price=1, tradeable=True),
        CanonicalPlayer(definition_id="X5", name="X5", rating=80, item_score=90, market_price=1, tradeable=True),
        CanonicalPlayer(definition_id="X6", name="X6", rating=80, item_score=90, market_price=1, tradeable=True),

        CanonicalPlayer(definition_id="Y1", name="Y1", rating=80, item_score=10, market_price=100, tradeable=True),
        CanonicalPlayer(definition_id="Y2", name="Y2", rating=80, item_score=10, market_price=100, tradeable=True),
        CanonicalPlayer(definition_id="Y3", name="Y3", rating=80, item_score=10, market_price=100, tradeable=True),
        CanonicalPlayer(definition_id="Y4", name="Y4", rating=80, item_score=10, market_price=100, tradeable=True),
        CanonicalPlayer(definition_id="Y5", name="Y5", rating=80, item_score=10, market_price=100, tradeable=True),
        CanonicalPlayer(definition_id="Y6", name="Y6", rating=80, item_score=10, market_price=100, tradeable=True),
    ]

    challenge = NormalizedChallenge(
        challenge_id="exact_1",
        name="Exact Streamlined",
        type="STREAMLINED",
        required_player_count=2,
        score_requirement=100
    )

    engine = MultiCompletionEngine(pool)
    completions = engine.solve(challenge, num_completions=6, mode="FAST_HEURISTIC")
    assert len(completions) < 6, f"Heuristic surprisingly found 6 completions: {completions}"

    completions_exact = engine.solve(challenge, num_completions=6, mode="EXACT")
    assert len(completions_exact) == 6, f"Exact failed, got {len(completions_exact)}"


def test_normal_exact_joint_allocation_avoids_greedy_trap():
    pool = [
        CanonicalPlayer(definition_id="100", instance_id="A", name="A", rating=80,
                        is_special=True, market_price=1, tradeable=True),
        CanonicalPlayer(definition_id="100", instance_id="B", name="B", rating=80,
                        is_special=True, market_price=1, tradeable=True),
        CanonicalPlayer(definition_id="101", instance_id="C", name="C", rating=80,
                        market_price=100, tradeable=True),
        CanonicalPlayer(definition_id="102", instance_id="D", name="D", rating=80,
                        market_price=100, tradeable=True),
    ]
    challenge = NormalizedChallenge(challenge_id="normal_joint", name="Normal",
        type="NORMAL", required_player_count=2,
        requirements=[Requirement(req_type="MIN_TOTW", val=1)])
    greedy_first = CPNormalSolver(pool).solve(challenge)
    assert {p.instance_id for p in greedy_first} == {"A", "B"}
    assert CPNormalSolver([p for p in pool if p.instance_id not in {"A", "B"}]).solve(challenge) is None
    result = MultiCompletionEngine(pool).solve_with_status(challenge, 2, "EXACT")
    assert result.success and result.metadata["mode"] == "EXACT"
    completions = result.metadata["completions"]
    assert len(completions) == 2
    assert all(sum(p.is_special for p in squad) >= 1 for squad in completions)
    ids = [p.instance_id for squad in completions for p in squad]
    assert len(ids) == len(set(ids)) == 4
