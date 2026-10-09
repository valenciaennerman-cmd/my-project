"""
Tests for SolverResult status semantics:
- OPTIMAL vs FEASIBLE vs INFEASIBLE vs SEARCH_LIMIT_REACHED
- search_truncated metadata exposure
- Streamlined safety limit distinction from domain limit
"""
import pytest
from app.services.sbc.models import (
    CanonicalPlayer, NormalizedChallenge, Requirement,
    SolverResult, SolverStatus,
)
from app.services.sbc.solver_streamlined import CPStreamlinedSolver, SOLVER_SAFETY_MAX_ITEMS
from app.services.sbc.solver_normal import CPNormalSolver
from app.services.sbc.multi_completion import MultiCompletionEngine


def _make_player(defn_id: str, score: int = 10, cost: int = 100, rating: int = 80, **kwargs) -> CanonicalPlayer:
    return CanonicalPlayer(
        definition_id=defn_id,
        name=f"Player_{defn_id}",
        rating=rating,
        item_score=score,
        market_price=cost,
        tradeable=True,
        **kwargs,
    )


# =========================================================
# Streamlined solver status semantics
# =========================================================

class TestStreamlinedSolverStatus:
    def test_unknown_is_search_limit(self, monkeypatch):
        from ortools.sat.python import cp_model
        monkeypatch.setattr(cp_model.CpSolver, "Solve", lambda self, model: cp_model.UNKNOWN)
        challenge = NormalizedChallenge(challenge_id="unknown", name="unknown", type="STREAMLINED", score_requirement=10)
        result = CPStreamlinedSolver([_make_player("A")]).solve_with_status(challenge)
        assert result.status == SolverStatus.SEARCH_LIMIT_REACHED

    def test_explicit_domain_max_above_safety_bound_reports_truncation(self):
        pool = [_make_player(str(i), score=1, cost=1) for i in range(SOLVER_SAFETY_MAX_ITEMS + 1)]
        challenge = NormalizedChallenge(challenge_id="large", name="large", type="STREAMLINED",
                                        score_requirement=151, max_player_count=151)
        result = CPStreamlinedSolver(pool).solve_with_status(challenge)
        assert result.status == SolverStatus.SEARCH_LIMIT_REACHED
        assert result.search_truncated
        assert result.solver_candidate_limit == SOLVER_SAFETY_MAX_ITEMS
        assert result.metadata["domain_player_limit"] == 151

    def test_optimal_status_on_solvable(self):
        pool = [_make_player(str(i), score=50, cost=100) for i in range(5)]
        challenge = NormalizedChallenge(
            challenge_id="t1", name="Test", type="STREAMLINED",
            score_requirement=50, required_player_count=5,
        )
        solver = CPStreamlinedSolver(pool)
        result = solver.solve_with_status(challenge)
        assert result.success
        assert result.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
        assert len(result.squad) >= 1

    def test_infeasible_status_on_impossible(self):
        pool = [_make_player(str(i), score=1, cost=100) for i in range(3)]
        challenge = NormalizedChallenge(
            challenge_id="t2", name="Test", type="STREAMLINED",
            score_requirement=99999, required_player_count=3,
        )
        solver = CPStreamlinedSolver(pool)
        result = solver.solve_with_status(challenge)
        assert not result.success
        assert result.status == SolverStatus.INFEASIBLE

    def test_empty_pool_is_infeasible(self):
        challenge = NormalizedChallenge(
            challenge_id="t3", name="Test", type="STREAMLINED",
            score_requirement=50,
        )
        solver = CPStreamlinedSolver([])
        result = solver.solve_with_status(challenge)
        assert result.status == SolverStatus.INFEASIBLE

    def test_zero_target_is_optimal(self):
        pool = [_make_player("1")]
        challenge = NormalizedChallenge(
            challenge_id="t4", name="Test", type="STREAMLINED",
            score_requirement=0,
        )
        solver = CPStreamlinedSolver(pool)
        result = solver.solve_with_status(challenge)
        assert result.status == SolverStatus.OPTIMAL

    def test_search_truncated_when_no_domain_limit_and_large_pool(self):
        """When no EA domain limit exists and pool > SOLVER_SAFETY_MAX_ITEMS,
        the result must indicate search_truncated=True."""
        pool = [_make_player(str(i), score=1, cost=1) for i in range(SOLVER_SAFETY_MAX_ITEMS + 10)]
        challenge = NormalizedChallenge(
            challenge_id="t5", name="Test", type="STREAMLINED",
            score_requirement=1,
            required_player_count=11,  # == 11 so treated as no domain limit
        )
        solver = CPStreamlinedSolver(pool)
        result = solver.solve_with_status(challenge)
        assert result.success  # Should still find a solution
        assert result.metadata.get("search_truncated") is True
        assert result.metadata.get("solver_candidate_limit") == SOLVER_SAFETY_MAX_ITEMS
        assert result.status == SolverStatus.FEASIBLE  # optimum is only within the safety bound

    def test_no_truncation_when_domain_limit_exists(self):
        """When an EA domain limit is provided (!=11), use that and don't flag truncation."""
        pool = [_make_player(str(i), score=50, cost=100) for i in range(20)]
        challenge = NormalizedChallenge(
            challenge_id="t6", name="Test", type="STREAMLINED",
            score_requirement=50,
            required_player_count=15,  # domain limit
        )
        solver = CPStreamlinedSolver(pool)
        result = solver.solve_with_status(challenge)
        assert result.success
        assert result.metadata.get("search_truncated") is not True
        assert result.metadata.get("domain_player_limit") == 15

    def test_legacy_solve_still_works(self):
        pool = [_make_player(str(i), score=50, cost=100) for i in range(5)]
        challenge = NormalizedChallenge(
            challenge_id="t7", name="Test", type="STREAMLINED",
            score_requirement=50, required_player_count=5,
        )
        solver = CPStreamlinedSolver(pool)
        result = solver.solve(challenge)
        assert result is not None
        assert len(result) >= 1


# =========================================================
# Normal solver status semantics
# =========================================================

class TestNormalSolverStatus:
    def test_unknown_is_search_limit(self, monkeypatch):
        from ortools.sat.python import cp_model
        monkeypatch.setattr(cp_model.CpSolver, "Solve", lambda self, model: cp_model.UNKNOWN)
        challenge = NormalizedChallenge(challenge_id="unknown", name="unknown", required_player_count=1)
        result = CPNormalSolver([_make_player("A")]).solve_with_status(challenge)
        assert result.status == SolverStatus.SEARCH_LIMIT_REACHED

    def test_optimal_on_solvable(self):
        pool = [_make_player(str(i), rating=83, cost=100, league_id=1, nation_id=1, club_id=i) for i in range(15)]
        challenge = NormalizedChallenge(
            challenge_id="n1", name="Test", type="NORMAL",
            required_player_count=11,
            requirements=[Requirement(req_type="TEAM_RATING", val=83, scope="MIN")],
        )
        solver = CPNormalSolver(pool)
        result = solver.solve_with_status(challenge)
        assert result.success
        assert result.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)

    def test_infeasible_on_impossible(self):
        pool = [_make_player(str(i), rating=50, cost=100) for i in range(15)]
        challenge = NormalizedChallenge(
            challenge_id="n2", name="Test", type="NORMAL",
            required_player_count=11,
            requirements=[Requirement(req_type="TEAM_RATING", val=99, scope="MIN")],
        )
        solver = CPNormalSolver(pool)
        result = solver.solve_with_status(challenge)
        assert not result.success
        assert result.status == SolverStatus.INFEASIBLE

    def test_empty_pool_is_infeasible(self):
        challenge = NormalizedChallenge(
            challenge_id="n3", name="Test", type="NORMAL",
            required_player_count=11,
        )
        solver = CPNormalSolver([])
        result = solver.solve_with_status(challenge)
        assert result.status == SolverStatus.INFEASIBLE


# =========================================================
# Multi-completion status semantics
# =========================================================

class TestMultiCompletionStatus:
    def test_exact_unknown_is_search_limit(self, monkeypatch):
        from ortools.sat.python import cp_model
        monkeypatch.setattr(cp_model.CpSolver, "Solve", lambda self, model: cp_model.UNKNOWN)
        challenge = NormalizedChallenge(challenge_id="unknown_multi", name="unknown",
                                        type="STREAMLINED", score_requirement=10)
        result = MultiCompletionEngine([_make_player("A", score=10)]).solve_with_status(challenge, 2, "EXACT")
        assert result.status == SolverStatus.SEARCH_LIMIT_REACHED

    def test_partial_fast_result_is_preserved(self):
        pool = [_make_player("A", score=100)]
        challenge = NormalizedChallenge(challenge_id="partial", name="partial", type="STREAMLINED", score_requirement=100)
        result = MultiCompletionEngine(pool).solve_with_status(challenge, 2, "FAST_HEURISTIC")
        assert result.status == SolverStatus.SEARCH_LIMIT_REACHED
        assert result.metadata["found"] == 1
        assert result.metadata["completions"][0][0].definition_id == "A"

    def test_exact_proof_preserves_feasible_partial_squad(self):
        pool = [_make_player("A", score=100, instance_id="A")]
        challenge = NormalizedChallenge(challenge_id="exact_partial", name="partial",
                                        type="STREAMLINED", score_requirement=100)
        result = MultiCompletionEngine(pool).solve_with_status(challenge, 2, "EXACT")
        assert result.status == SolverStatus.INFEASIBLE  # two completions are impossible
        assert result.metadata["found"] == 1
        assert result.metadata["completions"][0][0].instance_id == "A"

    def test_exact_rejects_duplicate_physical_instance_across_completions(self):
        pool = [_make_player("100", score=100, instance_id="A"),
                _make_player("100", score=100, instance_id="A")]
        challenge = NormalizedChallenge(challenge_id="duplicate", name="duplicate", type="STREAMLINED", score_requirement=100)
        result = MultiCompletionEngine(pool).solve_with_status(challenge, 2, "EXACT")
        assert result.status == SolverStatus.INFEASIBLE
    def test_exact_returns_proper_status(self):
        pool = [_make_player(str(i), score=100, cost=10) for i in range(10)]
        challenge = NormalizedChallenge(
            challenge_id="mc1", name="Test", type="STREAMLINED",
            score_requirement=100,
        )
        engine = MultiCompletionEngine(pool)
        result = engine.solve_with_status(challenge, num_completions=1, mode="EXACT")
        assert result.success
        assert result.metadata["mode"] == "EXACT"
        assert result.metadata["found"] == 1

    def test_fast_heuristic_returns_search_limit_on_failure(self):
        """FAST_HEURISTIC should return SEARCH_LIMIT_REACHED, not INFEASIBLE,
        when it can't find all completions."""
        pool = [_make_player(str(i), score=100, cost=10) for i in range(2)]
        challenge = NormalizedChallenge(
            challenge_id="mc2", name="Test", type="STREAMLINED",
            score_requirement=100,
        )
        engine = MultiCompletionEngine(pool)
        result = engine.solve_with_status(challenge, num_completions=10, mode="FAST_HEURISTIC")
        # Should not claim INFEASIBLE — heuristic can't prove it
        assert result.status != SolverStatus.INFEASIBLE
        assert result.status == SolverStatus.SEARCH_LIMIT_REACHED
        assert "FAST_HEURISTIC" in result.metadata.get("mode", "")

    def test_exact_infeasible_when_proven(self):
        """EXACT mode can legitimately return INFEASIBLE when CP-SAT proves no allocation."""
        pool = [_make_player("0", score=100, cost=10)]
        challenge = NormalizedChallenge(
            challenge_id="mc3", name="Test", type="STREAMLINED",
            score_requirement=100,
        )
        engine = MultiCompletionEngine(pool)
        result = engine.solve_with_status(challenge, num_completions=2, mode="EXACT")
        # Only 1 player for 2 completions — truly infeasible
        assert not result.success
        assert result.status == SolverStatus.INFEASIBLE

    def test_legacy_solve_backward_compatible(self):
        pool = [_make_player(str(i), score=100, cost=10) for i in range(5)]
        challenge = NormalizedChallenge(
            challenge_id="mc4", name="Test", type="STREAMLINED",
            score_requirement=100,
        )
        engine = MultiCompletionEngine(pool)
        completions = engine.solve(challenge, num_completions=1, mode="EXACT")
        assert isinstance(completions, list)
        assert len(completions) == 1
