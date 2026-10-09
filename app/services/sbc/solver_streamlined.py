from typing import List, Optional
from ortools.sat.python import cp_model
from .models import CanonicalPlayer, NormalizedChallenge, SolverResult, SolverStatus

SOLVER_SAFETY_MAX_ITEMS = 150

class CPStreamlinedSolver:
    """
    Minimum Cost Cover (Knapsack variant) Solver for EA FC Streamlined SBCs.
    Uses Google OR-Tools CP-SAT solver.
    """
    def __init__(self, pool: List[CanonicalPlayer]):
        self.pool = pool

    def solve(self, challenge: NormalizedChallenge, points_to_submit: Optional[int] = None, max_time_seconds: float = 5.0) -> Optional[List[CanonicalPlayer]]:
        """Legacy interface: returns list of players or None."""
        result = self.solve_with_status(challenge, points_to_submit, max_time_seconds)
        if result.success:
            return result.squad
        return None

    def solve_with_status(self, challenge: NormalizedChallenge, points_to_submit: Optional[int] = None, max_time_seconds: float = 5.0) -> SolverResult:
        """Returns SolverResult with precise status semantics."""
        if not self.pool:
            return SolverResult(status=SolverStatus.INFEASIBLE, metadata={"reason": "empty_pool"})

        target_score = points_to_submit if points_to_submit else challenge.score_requirement
        if not target_score or target_score <= 0:
            return SolverResult(status=SolverStatus.OPTIMAL, squad=[], metadata={"reason": "zero_target"})

        model = cp_model.CpModel()
        num_players = len(self.pool)

        # Variables
        x = [model.NewBoolVar(f"x_{i}") for i in range(num_players)]

        # Instance ID constraint
        instance_players = {}
        for i, p in enumerate(self.pool):
            instance_players.setdefault(p.instance_id or f"unknown:{p.definition_id}", []).append(i)
        for indices in instance_players.values():
            model.Add(sum(x[i] for i in indices) <= 1)
        for i, p in enumerate(self.pool):
            if not p.instance_id:
                model.Add(x[i] + sum(x[j] for j, other in enumerate(self.pool)
                                     if other.instance_id and other.definition_id == p.definition_id) <= 1)

        # UNVERIFIED_DOMAIN_RULE: Does EA forbid duplicate definitions (same player, different physical cards) in a single squad?
        # If not established for FC27, document as UNVERIFIED_DOMAIN_RULE and only enforce unique `instance_id`.
        # (definition_id constraint removed to allow duplicate players if they have different instances)

        # Locked and Excluded Constraints
        for i, p in enumerate(self.pool):
            if p.locked:
                model.Add(x[i] == 1)
            if p.excluded:
                model.Add(x[i] == 0)

        # Player count constraints — distinguish domain limit from safety limit
        domain_limit = challenge.max_player_count
        if domain_limit is None and challenge.required_player_count != 11:
            domain_limit = challenge.required_player_count

        effective_limit = domain_limit if domain_limit is not None else SOLVER_SAFETY_MAX_ITEMS
        max_players = min(effective_limit, SOLVER_SAFETY_MAX_ITEMS, num_players)

        # Track whether the safety bound actually truncated the search
        search_truncated = (domain_limit is None or domain_limit > SOLVER_SAFETY_MAX_ITEMS) and num_players > SOLVER_SAFETY_MAX_ITEMS

        model.Add(sum(x) <= max_players)
        model.Add(sum(x) >= (challenge.min_player_count or 1))

        # Main Score Constraint
        item_scores = [p.item_score for p in self.pool]
        total_score_expr = sum(item_scores[i] * x[i] for i in range(num_players))
        model.Add(total_score_expr >= target_score)

        # Optimization Objective
        # 1. Minimize Effective Cost
        # 2. Minimize Overshoot (total_score_expr - target_score)
        # Lexicographic combination
        effective_costs = [p.effective_cost for p in self.pool]
        total_cost_expr = sum(effective_costs[i] * x[i] for i in range(num_players))

        # Cost is highest priority, overshoot is secondary
        # To avoid overflow while preserving strict priority, multiplier must be > max possible overshoot
        max_possible_overshoot = sum(item_scores)
        multiplier = max_possible_overshoot + 1
        model.Minimize(total_cost_expr * multiplier + total_score_expr)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max_time_seconds

        status = solver.Solve(model)

        result_metadata = {}
        if search_truncated:
            result_metadata["search_truncated"] = True
            result_metadata["solver_candidate_limit"] = SOLVER_SAFETY_MAX_ITEMS
        if domain_limit is not None:
            result_metadata["domain_player_limit"] = domain_limit

        if status == cp_model.OPTIMAL:
            selected = [self.pool[i] for i in range(num_players) if solver.Value(x[i])]
            return SolverResult(status=SolverStatus.FEASIBLE if search_truncated else SolverStatus.OPTIMAL,
                                squad=selected, metadata=result_metadata)
        elif status == cp_model.FEASIBLE:
            selected = [self.pool[i] for i in range(num_players) if solver.Value(x[i])]
            return SolverResult(status=SolverStatus.FEASIBLE, squad=selected, metadata=result_metadata)
        elif status == cp_model.INFEASIBLE:
            if search_truncated:
                # We cannot prove true infeasibility if we truncated the search space
                result_metadata["diagnostic"] = "Infeasible within truncated search space; full pool may have solutions."
                return SolverResult(status=SolverStatus.SEARCH_LIMIT_REACHED, metadata=result_metadata)
            return SolverResult(status=SolverStatus.INFEASIBLE, metadata=result_metadata)
        elif status == cp_model.UNKNOWN:
            # Solver stopped without proving feasibility or infeasibility (time/resource bound)
            result_metadata["diagnostic"] = "Solver reached time or resource limit without determining feasibility."
            return SolverResult(status=SolverStatus.SEARCH_LIMIT_REACHED, metadata=result_metadata)
        else:
            return SolverResult(status=SolverStatus.ERROR, metadata={"cp_sat_status": status})
