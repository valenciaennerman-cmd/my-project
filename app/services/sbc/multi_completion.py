from typing import List, Optional
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge, SolverResult, SolverStatus
from app.services.sbc.solver_normal import CPNormalSolver
from app.services.sbc.solver_streamlined import CPStreamlinedSolver, SOLVER_SAFETY_MAX_ITEMS
from ortools.sat.python import cp_model

class MultiCompletionEngine:
    def __init__(self, pool: List[CanonicalPlayer]):
        self.pool = pool

    def solve(self, challenge: NormalizedChallenge, num_completions: int = 1, mode: str = "EXACT") -> List[List[CanonicalPlayer]]:
        """Legacy interface: returns list of completions (may be partial)."""
        result = self.solve_with_status(challenge, num_completions, mode)
        # Return whatever completions were found, even partial (SEARCH_LIMIT_REACHED)
        return result.metadata.get("completions", [])

    def solve_with_status(self, challenge: NormalizedChallenge, num_completions: int = 1, mode: str = "EXACT") -> SolverResult:
        """Returns SolverResult with precise status semantics."""
        if mode == "EXACT":
            return self._solve_exact(challenge, num_completions)
        elif mode == "FAST_HEURISTIC":
            completions = self._solve_fast_heuristic(challenge, num_completions)
            if completions and len(completions) == num_completions:
                return SolverResult(
                    status=SolverStatus.FEASIBLE,
                    metadata={"completions": completions, "mode": "FAST_HEURISTIC",
                              "requested": num_completions, "found": len(completions)}
                )
            elif completions:
                # Found some but not all requested completions —
                # FAST_HEURISTIC cannot prove infeasibility
                return SolverResult(
                    status=SolverStatus.SEARCH_LIMIT_REACHED,
                    metadata={"completions": completions, "mode": "FAST_HEURISTIC",
                              "requested": num_completions, "found": len(completions),
                              "diagnostic": "Heuristic found fewer completions than requested. "
                                            "This does NOT prove infeasibility. Use EXACT mode for completeness."}
                )
            else:
                return SolverResult(
                    status=SolverStatus.SEARCH_LIMIT_REACHED,
                    metadata={"completions": [], "mode": "FAST_HEURISTIC",
                              "requested": num_completions, "found": 0,
                              "diagnostic": "Heuristic found no completions. "
                                            "This does NOT prove infeasibility. Use EXACT mode for completeness."}
                )
        else:
            raise ValueError(f"Unknown completion mode: {mode}")

    def _solve_exact(self, challenge: NormalizedChallenge, num_completions: int) -> SolverResult:
        if not self.pool or num_completions <= 0:
            return SolverResult(status=SolverStatus.INFEASIBLE, metadata={"reason": "empty_pool_or_zero_completions"})

        model = cp_model.CpModel()
        num_players = len(self.pool)

        # x[i][c] is 1 if player i is in completion c
        x = [[model.NewBoolVar(f"x_{i}_{c}") for c in range(num_completions)] for i in range(num_players)]

        # Each player used at most once across all completions
        for i in range(num_players):
            model.Add(sum(x[i][c] for c in range(num_completions)) <= 1)
        by_instance = {}
        for i, player in enumerate(self.pool):
            by_instance.setdefault(player.instance_id or f"unknown:{player.definition_id}", []).append(i)
        for indices in by_instance.values():
            model.Add(sum(x[i][c] for i in indices for c in range(num_completions)) <= 1)
        for i, player in enumerate(self.pool):
            if not player.instance_id:
                model.Add(sum(x[i][c] for c in range(num_completions)) +
                          sum(x[j][c] for j, other in enumerate(self.pool)
                              if other.instance_id and other.definition_id == player.definition_id
                              for c in range(num_completions)) <= 1)

        # Locked/Excluded constraints
        for i, p in enumerate(self.pool):
            if p.excluded:
                for c in range(num_completions):
                    model.Add(x[i][c] == 0)
            if p.locked:
                model.Add(sum(x[i][c] for c in range(num_completions)) == 1)

        if challenge.type == "NORMAL":
            search_truncated = False
            domain_limit = None
            normal_solver = CPNormalSolver(self.pool)
            try:
                for c in range(num_completions):
                    normal_solver.add_constraints(model, [x[i][c] for i in range(num_players)],
                                                  challenge, enforce_locked=False)
            except ValueError as exc:
                return SolverResult(status=SolverStatus.ERROR, metadata={"diagnostic": str(exc)})
            total_cost = sum(p.effective_cost * x[i][c]
                             for i, p in enumerate(self.pool) for c in range(num_completions))
            rating_penalty = sum(p.rating * 10 * x[i][c]
                                 for i, p in enumerate(self.pool) for c in range(num_completions))
            model.Minimize(total_cost * 1000 + rating_penalty)
        elif challenge.type == "STREAMLINED":
            target_score = challenge.score_requirement
            if target_score is None or target_score <= 0:
                return SolverResult(status=SolverStatus.ERROR, metadata={"diagnostic": "Positive score target required"})
            item_scores = [p.item_score for p in self.pool]
            effective_costs = [p.effective_cost for p in self.pool]

            # Distinguish domain limit from safety limit
            domain_limit = challenge.max_player_count
            if domain_limit is None and challenge.required_player_count != 11:
                domain_limit = challenge.required_player_count

            effective_limit = domain_limit if domain_limit is not None else SOLVER_SAFETY_MAX_ITEMS
            max_players = min(effective_limit, SOLVER_SAFETY_MAX_ITEMS, num_players)
            search_truncated = (domain_limit is None or domain_limit > SOLVER_SAFETY_MAX_ITEMS) and num_players > SOLVER_SAFETY_MAX_ITEMS

            total_cost_expr = 0
            total_score_expr = 0

            for c in range(num_completions):
                model.Add(sum(x[i][c] for i in range(num_players)) <= max_players)
                model.Add(sum(x[i][c] for i in range(num_players)) >= (challenge.min_player_count or 1))

                score_c = sum(item_scores[i] * x[i][c] for i in range(num_players))
                model.Add(score_c >= target_score)
                total_score_expr += score_c

                cost_c = sum(effective_costs[i] * x[i][c] for i in range(num_players))
                total_cost_expr += cost_c

                # Instance ID constraint for THIS completion
                instance_players = {}
                for i, p in enumerate(self.pool):
                    instance_players.setdefault(p.instance_id or f"unknown:{p.definition_id}", []).append(i)
                for indices in instance_players.values():
                    model.Add(sum(x[i][c] for i in indices) <= 1)

            max_possible_overshoot = sum(item_scores) * num_completions
            multiplier = max_possible_overshoot + 1
            model.Minimize(total_cost_expr * multiplier + total_score_expr)

        else:
            return SolverResult(status=SolverStatus.ERROR, metadata={"diagnostic": "Unsupported challenge type"})

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30.0

        status = solver.Solve(model)

        result_metadata = {
            "mode": "EXACT",
            "requested": num_completions,
        }
        if search_truncated:
            result_metadata["search_truncated"] = True
            result_metadata["solver_candidate_limit"] = SOLVER_SAFETY_MAX_ITEMS
        if domain_limit is not None:
            result_metadata["domain_player_limit"] = domain_limit

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            completions = []
            for c in range(num_completions):
                comp = [self.pool[i] for i in range(num_players) if solver.Value(x[i][c])]
                completions.append(comp)
            result_metadata["completions"] = completions
            result_metadata["found"] = len(completions)
            solver_status = SolverStatus.OPTIMAL if status == cp_model.OPTIMAL and not search_truncated else SolverStatus.FEASIBLE
            return SolverResult(status=solver_status, metadata=result_metadata)
        elif status == cp_model.INFEASIBLE:
            if search_truncated:
                result_metadata["diagnostic"] = "Infeasible within truncated search space; full pool may have solutions."
                partial = self._solve_fast_heuristic(challenge, num_completions)
                result_metadata["found"] = len(partial)
                result_metadata["completions"] = partial
                return SolverResult(status=SolverStatus.SEARCH_LIMIT_REACHED, metadata=result_metadata)
            partial = self._solve_fast_heuristic(challenge, num_completions)
            result_metadata["found"] = len(partial)
            result_metadata["completions"] = partial
            return SolverResult(status=SolverStatus.INFEASIBLE, metadata=result_metadata)
        elif status == cp_model.UNKNOWN:
            result_metadata["diagnostic"] = "Solver reached time or resource limit without determining feasibility."
            result_metadata["found"] = 0
            result_metadata["completions"] = []
            return SolverResult(status=SolverStatus.SEARCH_LIMIT_REACHED, metadata=result_metadata)
        else:
            result_metadata["completions"] = []
            result_metadata["found"] = 0
            return SolverResult(status=SolverStatus.ERROR, metadata={"cp_sat_status": status})

    def _solve_fast_heuristic(self, challenge: NormalizedChallenge, num_completions: int) -> List[List[CanonicalPlayer]]:
        best_completions = []

        def search(current_pool: List[CanonicalPlayer], current_completions: List[List[CanonicalPlayer]], depth: int) -> bool:
            nonlocal best_completions

            if len(current_completions) > len(best_completions):
                best_completions = list(current_completions)

            if len(current_completions) == num_completions:
                return True

            if not current_pool:
                return False

            banned_from_c = set()
            max_retries = 5

            for attempt in range(max_retries):
                c_pool = [p for p in current_pool if (p.instance_id or p.definition_id) not in banned_from_c]
                if not c_pool:
                    break

                if challenge.type == "STREAMLINED":
                    solver = CPStreamlinedSolver(c_pool)
                else:
                    solver = CPNormalSolver(c_pool)

                result = solver.solve(challenge)
                if not result:
                    break

                used_ids = {p.instance_id or p.definition_id for p in result}
                next_pool = [p for p in current_pool if (p.instance_id or p.definition_id) not in used_ids]

                current_completions.append(result)
                if search(next_pool, current_completions, depth + 1):
                    return True
                current_completions.pop()

                result_sorted = sorted(result, key=lambda x: x.effective_cost)
                if result_sorted:
                    banned_from_c.add(result_sorted[0].instance_id or result_sorted[0].definition_id)
                else:
                    break

            return False

        search(self.pool, [], 0)
        return best_completions
