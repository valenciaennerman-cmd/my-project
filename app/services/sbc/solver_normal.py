from typing import List, Optional
from ortools.sat.python import cp_model
from .models import CanonicalPlayer, NormalizedChallenge, SolverResult, SolverStatus
from .chemistry import ACTIVE_CHEMISTRY_RULES

class CPNormalSolver:
    """
    Mathematical Constraint Programming Solver for EA FC Normal SBCs.
    Uses Google OR-Tools CP-SAT solver.
    """
    def __init__(self, pool: List[CanonicalPlayer]):
        self.pool = pool

    def solve(self, challenge: NormalizedChallenge, max_time_seconds: float = 5.0, minimize_changes_from: Optional[List[CanonicalPlayer]] = None, locked_definition_ids: Optional[List[str]] = None) -> Optional[List[CanonicalPlayer]]:
        """Legacy interface: returns list of players or None."""
        result = self.solve_with_status(challenge, max_time_seconds, minimize_changes_from, locked_definition_ids)
        if result.success:
            return result.squad
        return None

    def add_constraints(self, model: cp_model.CpModel, x: list, challenge: NormalizedChallenge,
                        locked_definition_ids: Optional[List[str]] = None, enforce_locked: bool = True) -> None:
        """Add one normal completion to a CP-SAT model."""
        num_players = len(self.pool)
        req_count = challenge.required_player_count
        model.Add(sum(x) == req_count)

        # Enforce locked players
        for i in range(num_players):
            if enforce_locked and self.pool[i].locked:
                model.Add(x[i] == 1)
            elif self.pool[i].excluded:
                model.Add(x[i] == 0)

        if enforce_locked and locked_definition_ids:
            locked_set = set(locked_definition_ids)
            for i, p in enumerate(self.pool):
                if (p.instance_id or p.definition_id) in locked_set:
                    model.Add(x[i] == 1)

        # Instance ID constraint: Cannot select the exact same instance twice
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

        # Constraints parsing
        min_rating = 0
        min_totw = 0

        for req in challenge.requirements:
            if req.req_type == "TEAM_RATING" and req.scope == "MIN":
                min_rating = req.val
            elif req.req_type == "MIN_TOTW" and req.scope == "MIN":
                min_totw = req.val
        if min_rating and req_count != 11:
            raise ValueError("EA-style rating is supported only for 11-player normal squads")

        # Category tracking
        leagues = {p.league_id for p in self.pool if p.league_id is not None}
        nations = {p.nation_id for p in self.pool if p.nation_id is not None}
        clubs = {p.club_id for p in self.pool if p.club_id is not None}

        league_players = {l: [] for l in leagues}
        nation_players = {n: [] for n in nations}
        club_players = {c: [] for c in clubs}

        for i, p in enumerate(self.pool):
            if p.league_id is not None: league_players[p.league_id].append(i)
            if p.nation_id is not None: nation_players[p.nation_id].append(i)
            if p.club_id is not None: club_players[p.club_id].append(i)

        league_counts = {l: model.NewIntVar(0, req_count, f"count_league_{l}") for l in leagues}
        nation_counts = {n: model.NewIntVar(0, req_count, f"count_nation_{n}") for n in nations}
        club_counts = {c: model.NewIntVar(0, req_count, f"count_club_{c}") for c in clubs}

        for l, p_indices in league_players.items(): model.Add(league_counts[l] == sum(x[i] for i in p_indices))
        for n, p_indices in nation_players.items(): model.Add(nation_counts[n] == sum(x[i] for i in p_indices))
        for c, p_indices in club_players.items(): model.Add(club_counts[c] == sum(x[i] for i in p_indices))

        league_used = {l: model.NewBoolVar(f"used_league_{l}") for l in leagues}
        nation_used = {n: model.NewBoolVar(f"used_nation_{n}") for n in nations}
        club_used = {c: model.NewBoolVar(f"used_club_{c}") for c in clubs}

        for l in leagues:
            model.Add(league_counts[l] > 0).OnlyEnforceIf(league_used[l])
            model.Add(league_counts[l] == 0).OnlyEnforceIf(league_used[l].Not())
        for n in nations:
            model.Add(nation_counts[n] > 0).OnlyEnforceIf(nation_used[n])
            model.Add(nation_counts[n] == 0).OnlyEnforceIf(nation_used[n].Not())
        for c in clubs:
            model.Add(club_counts[c] > 0).OnlyEnforceIf(club_used[c])
            model.Add(club_counts[c] == 0).OnlyEnforceIf(club_used[c].Not())

        total_leagues = sum(league_used.values()) if leagues else 0
        total_nations = sum(nation_used.values()) if nations else 0
        total_clubs = sum(club_used.values()) if clubs else 0

        max_same_league = model.NewIntVar(0, req_count, "max_same_league")
        if leagues: model.AddMaxEquality(max_same_league, list(league_counts.values()))
        else: model.Add(max_same_league == 0)

        max_same_nation = model.NewIntVar(0, req_count, "max_same_nation")
        if nations: model.AddMaxEquality(max_same_nation, list(nation_counts.values()))
        else: model.Add(max_same_nation == 0)

        max_same_club = model.NewIntVar(0, req_count, "max_same_club")
        if clubs: model.AddMaxEquality(max_same_club, list(club_counts.values()))
        else: model.Add(max_same_club == 0)

        min_chem = 0

        for req in challenge.requirements:
            req_type = req.req_type.upper()
            scope = req.scope.upper()

            if req_type == "TEAM_RATING" and scope == "MIN":
                pass
            elif req_type == "MIN_TOTW" and scope == "MIN":
                pass
            elif req_type in ["MIN_CHEM", "CHEM"]:
                if scope == "MIN" or req_type == "MIN_CHEM":
                    min_chem = req.val
            elif "LEAGUE" in req_type:
                if req_type in ["MIN_LEAGUES", "MAX_LEAGUES", "EXACT_LEAGUES", "LEAGUES", "MIN_LEAGUE_COUNT", "MAX_LEAGUE_COUNT", "EXACT_LEAGUE_COUNT", "LEAGUE_COUNT"]:
                    if scope == "MIN" or "MIN" in req_type: model.Add(total_leagues >= req.val)
                    elif scope == "MAX" or "MAX" in req_type: model.Add(total_leagues <= req.val)
                    elif scope == "EXACT" or "EXACT" in req_type: model.Add(total_leagues == req.val)
                elif req_type == "SAME_LEAGUE_COUNT":
                    if scope == "MIN": model.Add(max_same_league >= req.val)
                    elif scope == "MAX": model.Add(max_same_league <= req.val)
                    elif scope == "EXACT": model.Add(max_same_league == req.val)
                else:
                    raise ValueError(f"UNSUPPORTED_REQUIREMENT: {req_type}")
            elif "NATION" in req_type:
                if req_type in ["MIN_NATIONS", "MAX_NATIONS", "EXACT_NATIONS", "NATIONS", "MIN_NATION_COUNT", "MAX_NATION_COUNT", "EXACT_NATION_COUNT", "NATION_COUNT"]:
                    if scope == "MIN" or "MIN" in req_type: model.Add(total_nations >= req.val)
                    elif scope == "MAX" or "MAX" in req_type: model.Add(total_nations <= req.val)
                    elif scope == "EXACT" or "EXACT" in req_type: model.Add(total_nations == req.val)
                elif req_type == "SAME_NATION_COUNT":
                    if scope == "MIN": model.Add(max_same_nation >= req.val)
                    elif scope == "MAX": model.Add(max_same_nation <= req.val)
                    elif scope == "EXACT": model.Add(max_same_nation == req.val)
                else:
                    raise ValueError(f"UNSUPPORTED_REQUIREMENT: {req_type}")
            elif "CLUB" in req_type:
                if req_type in ["MIN_CLUBS", "MAX_CLUBS", "EXACT_CLUBS", "CLUBS", "MIN_CLUB_COUNT", "MAX_CLUB_COUNT", "EXACT_CLUB_COUNT", "CLUB_COUNT"]:
                    if scope == "MIN" or "MIN" in req_type: model.Add(total_clubs >= req.val)
                    elif scope == "MAX" or "MAX" in req_type: model.Add(total_clubs <= req.val)
                    elif scope == "EXACT" or "EXACT" in req_type: model.Add(total_clubs == req.val)
                elif req_type == "SAME_CLUB_COUNT":
                    if scope == "MIN": model.Add(max_same_club >= req.val)
                    elif scope == "MAX": model.Add(max_same_club <= req.val)
                    elif scope == "EXACT": model.Add(max_same_club == req.val)
                else:
                    raise ValueError(f"UNSUPPORTED_REQUIREMENT: {req_type}")
            elif "RARE" in req_type:
                rare_expr = sum(x[i] for i in range(num_players) if self.pool[i].is_rare)
                if scope == "MIN" or req_type == "MIN_RARE": model.Add(rare_expr >= req.val)
                elif scope == "MAX" or req_type == "MAX_RARE": model.Add(rare_expr <= req.val)
                elif scope == "EXACT" or req_type == "EXACT_RARE": model.Add(rare_expr == req.val)
            else:
                raise ValueError(f"UNSUPPORTED_REQUIREMENT: {req_type}")

        if min_chem > 0:
            rules = ACTIVE_CHEMISTRY_RULES
            club_pts = {c: model.NewIntVar(0, req_count, f"club_pts_{c}") for c in clubs}
            nation_pts = {n: model.NewIntVar(0, req_count + 22, f"nation_pts_{n}") for n in nations}
            league_pts = {l: model.NewIntVar(0, req_count + 22, f"league_pts_{l}") for l in leagues}

            total_icons = model.NewIntVar(0, req_count, "total_icons")
            model.Add(total_icons == sum(x[i] for i in range(num_players) if self.pool[i].is_icon))

            for c in clubs:
                model.Add(club_pts[c] == club_counts[c])

            for n in nations:
                n_base = sum(x[i] for i in nation_players[n] if not self.pool[i].is_icon and not self.pool[i].is_hero)
                n_icons = sum(x[i] for i in nation_players[n] if self.pool[i].is_icon)
                n_heroes = sum(x[i] for i in nation_players[n] if self.pool[i].is_hero)
                model.Add(nation_pts[n] == n_base + rules["icon_nation_weight"] * n_icons + rules["hero_nation_weight"] * n_heroes)

            for l in leagues:
                l_base = sum(x[i] for i in league_players[l] if not self.pool[i].is_hero and not self.pool[i].is_icon)
                l_heroes = sum(x[i] for i in league_players[l] if self.pool[i].is_hero)
                model.Add(league_pts[l] == l_base + rules["hero_league_weight"] * l_heroes + rules["icon_league_weight"] * total_icons)

            club_chem = {c: model.NewIntVar(0, 3, f"club_chem_{c}") for c in clubs}
            nation_chem = {n: model.NewIntVar(0, 3, f"nation_chem_{n}") for n in nations}
            league_chem = {l: model.NewIntVar(0, 3, f"league_chem_{l}") for l in leagues}

            def add_thresholds(pts_var, chem_var, t1, t2, t3, prefix):
                b1 = model.NewBoolVar(f"{prefix}_b1")
                b2 = model.NewBoolVar(f"{prefix}_b2")
                b3 = model.NewBoolVar(f"{prefix}_b3")
                model.Add(pts_var >= t1).OnlyEnforceIf(b1)
                model.Add(pts_var < t1).OnlyEnforceIf(b1.Not())
                model.Add(pts_var >= t2).OnlyEnforceIf(b2)
                model.Add(pts_var < t2).OnlyEnforceIf(b2.Not())
                model.Add(pts_var >= t3).OnlyEnforceIf(b3)
                model.Add(pts_var < t3).OnlyEnforceIf(b3.Not())
                model.Add(chem_var == b1 + b2 + b3)

            for c in clubs: add_thresholds(club_pts[c], club_chem[c], *sorted(rules["club_thresholds"]), f"c_{c}")
            for n in nations: add_thresholds(nation_pts[n], nation_chem[n], *sorted(rules["nation_thresholds"]), f"n_{n}")
            for l in leagues: add_thresholds(league_pts[l], league_chem[l], *sorted(rules["league_thresholds"]), f"l_{l}")

            player_chem = []
            for i, p in enumerate(self.pool):
                p_chem = model.NewIntVar(0, 3, f"p_chem_{i}")
                player_chem.append(p_chem)
                model.Add(p_chem == 0).OnlyEnforceIf(x[i].Not())
                if p.is_icon or p.is_hero:
                    model.Add(p_chem == (rules["icon_chem"] if p.is_icon else rules["hero_chem"])).OnlyEnforceIf(x[i])
                else:
                    raw = model.NewIntVar(0, 9, f"raw_chem_{i}")
                    c_val = club_chem[p.club_id] if p.club_id is not None else 0
                    n_val = nation_chem[p.nation_id] if p.nation_id is not None else 0
                    l_val = league_chem[p.league_id] if p.league_id is not None else 0

                    c_val_expr = c_val if isinstance(c_val, cp_model.IntVar) else 0
                    n_val_expr = n_val if isinstance(n_val, cp_model.IntVar) else 0
                    l_val_expr = l_val if isinstance(l_val, cp_model.IntVar) else 0

                    model.Add(raw == c_val_expr + n_val_expr + l_val_expr)

                    b_cap = model.NewBoolVar(f"cap_chem_{i}")
                    model.Add(raw >= 3).OnlyEnforceIf(b_cap)
                    model.Add(raw < 3).OnlyEnforceIf(b_cap.Not())

                    model.Add(p_chem == 3).OnlyEnforceIf([b_cap, x[i]])
                    model.Add(p_chem == raw).OnlyEnforceIf([b_cap.Not(), x[i]])

            model.Add(sum(player_chem) >= min_chem)

        # Rating Constraint (EA Formula)
        # base_avg = S // 11
        # Final Rating = (S + sum(max(0, R_i - base_avg))) // 11 >= target
        # => S + sum(C_i) >= 11 * target
        if min_rating > 0:
            S = sum(self.pool[i].rating * x[i] for i in range(num_players))

            # S is bounded between 0 and req_count * 99
            S_var = model.NewIntVar(0, req_count * 99, "S_var")
            model.Add(S_var == S)

            base_avg = model.NewIntVar(0, 99, "base_avg")
            model.AddDivisionEquality(base_avg, S_var, 11)

            C_vars = []
            for i in range(num_players):
                # C_i = max(0, rating - base_avg) if x_i == 1 else 0
                C_i = model.NewIntVar(0, 99, f"C_{i}")

                # If x_i == 0, C_i = 0
                model.Add(C_i == 0).OnlyEnforceIf(x[i].Not())

                # If x_i == 1, C_i = max(0, rating - base_avg)
                diff_i = model.NewIntVar(-99, 99, f"diff_{i}")
                model.Add(diff_i == self.pool[i].rating - base_avg)

                max_diff_i = model.NewIntVar(0, 99, f"max_diff_{i}")
                model.AddMaxEquality(max_diff_i, [0, diff_i])

                model.Add(C_i == max_diff_i).OnlyEnforceIf(x[i])

                C_vars.append(C_i)

            model.Add(S_var + sum(C_vars) >= 11 * min_rating)

        # TOTW / Special Constraint
        if min_totw > 0:
            model.Add(sum(x[i] for i in range(num_players) if self.pool[i].is_special) >= min_totw)


    def solve_with_status(self, challenge: NormalizedChallenge, max_time_seconds: float = 5.0, minimize_changes_from: Optional[List[CanonicalPlayer]] = None, locked_definition_ids: Optional[List[str]] = None) -> SolverResult:
        if not self.pool:
            return SolverResult(status=SolverStatus.INFEASIBLE, metadata={"reason": "empty_pool"})

        model = cp_model.CpModel()
        num_players = len(self.pool)
        x = [model.NewBoolVar(f"x_{i}") for i in range(num_players)]
        if challenge.required_player_count != 11 and any(
            req.req_type == "TEAM_RATING" and req.scope == "MIN" for req in challenge.requirements
        ):
            return SolverResult(status=SolverStatus.ERROR, metadata={
                "diagnostic": "EA-style rating is supported only for 11-player normal squads"})
        self.add_constraints(model, x, challenge, locked_definition_ids)

        # Objective: Minimize Effective Cost + Overshoot Penalty + Rarity Penalty
        # Minimize effective cost primarily
        effective_costs = [p.effective_cost for p in self.pool]
        total_cost_expr = sum(effective_costs[i] * x[i] for i in range(num_players))

        # Add penalty for higher ratings to save fodder (overshoot penalty)
        overshoot_penalty = sum((self.pool[i].rating * 10) * x[i] for i in range(num_players))

        if minimize_changes_from:
            current_squad_ids = {p.instance_id or p.definition_id for p in minimize_changes_from}
            changes = []
            for i, p in enumerate(self.pool):
                if (p.instance_id or p.definition_id) in current_squad_ids:
                    dropped = model.NewBoolVar(f"dropped_{i}")
                    model.Add(dropped == 1 - x[i])
                    changes.append(dropped)
                else:
                    changes.append(x[i])
            total_changes = sum(changes)
            model.Minimize(total_changes * 1000000 + total_cost_expr)
        else:
            model.Minimize(total_cost_expr * 1000 + overshoot_penalty)

        # Solver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max_time_seconds
        # solver.parameters.log_search_progress = True

        status = solver.Solve(model)

        if status == cp_model.OPTIMAL:
            selected_players = [self.pool[i] for i in range(num_players) if solver.Value(x[i])]
            return SolverResult(status=SolverStatus.OPTIMAL, squad=selected_players)
        elif status == cp_model.FEASIBLE:
            selected_players = [self.pool[i] for i in range(num_players) if solver.Value(x[i])]
            return SolverResult(status=SolverStatus.FEASIBLE, squad=selected_players)
        elif status == cp_model.INFEASIBLE:
            return SolverResult(status=SolverStatus.INFEASIBLE)
        elif status == cp_model.UNKNOWN:
            return SolverResult(status=SolverStatus.SEARCH_LIMIT_REACHED,
                              metadata={"diagnostic": "Solver reached time or resource limit without determining feasibility."})
        else:
            return SolverResult(status=SolverStatus.ERROR, metadata={"cp_sat_status": status})
