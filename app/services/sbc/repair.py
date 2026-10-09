from typing import List, Optional
from ortools.sat.python import cp_model
from .models import CanonicalPlayer, NormalizedChallenge

class RepairEngine:
    @staticmethod
    def repair_squad(
        current_squad: List[CanonicalPlayer],
        challenge: NormalizedChallenge,
        pool: List[CanonicalPlayer],
        locked_definition_ids: List[str],
        is_streamlined: bool = False
    ) -> Optional[List[CanonicalPlayer]]:
        """
        Repairs the squad by changing the minimum number of unlocked items
        to make the squad valid again using CP-SAT.
        """
        # Ensure all items in current_squad are in pool
        pool_ids = {p.instance_id or p.definition_id for p in pool}
        combined_pool = list(pool)
        for p in current_squad:
            if (p.instance_id or p.definition_id) not in pool_ids:
                combined_pool.append(p)
                pool_ids.add(p.instance_id or p.definition_id)

        if not combined_pool:
            return None

        if not is_streamlined:
            from .solver_normal import CPNormalSolver
            solver = CPNormalSolver(combined_pool)
            return solver.solve(challenge, max_time_seconds=5.0, minimize_changes_from=current_squad, locked_definition_ids=locked_definition_ids)

        model = cp_model.CpModel()
        num_players = len(combined_pool)
        x = [model.NewBoolVar(f"x_{i}") for i in range(num_players)]

        req_count = challenge.required_player_count
        model.Add(sum(x) == req_count)

        # Enforce locked items
        for i, p in enumerate(combined_pool):
            if (p.instance_id or p.definition_id) in locked_definition_ids:
                model.Add(x[i] == 1)

        # Constraints parsing
        min_totw = 0
        for req in challenge.requirements:
            if req.req_type == "MIN_TOTW" and req.scope == "MIN":
                min_totw = req.val

        # Streamlined Score Constraint
        target_score = challenge.score_requirement or 0
        if target_score > 0:
            model.Add(sum(combined_pool[i].item_score * x[i] for i in range(num_players)) >= target_score)

        # TOTW / Special Constraint
        if min_totw > 0:
            model.Add(sum(x[i] for i in range(num_players) if combined_pool[i].is_special) >= min_totw)

        # Objective: Minimize number of changes from current_squad
        current_squad_ids = {p.instance_id or p.definition_id for p in current_squad}

        changes = []
        for i, p in enumerate(combined_pool):
            if (p.instance_id or p.definition_id) in current_squad_ids:
                dropped = model.NewBoolVar(f"dropped_{i}")
                model.Add(dropped == 1 - x[i])
                changes.append(dropped)
            else:
                changes.append(x[i])

        total_changes = sum(changes)
        total_cost = sum(combined_pool[i].effective_cost * x[i] for i in range(num_players))

        model.Minimize(total_changes * 1000000 + total_cost)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5.0
        status = solver.Solve(model)

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            return [combined_pool[i] for i in range(num_players) if solver.Value(x[i])]

        return None
