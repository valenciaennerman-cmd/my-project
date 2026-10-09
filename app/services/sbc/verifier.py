from typing import List, Dict, Any
import math
from collections import Counter
from .models import CanonicalPlayer, NormalizedChallenge
from .chemistry import calculate_chemistry

class IndependentVerifier:
    """
    Independently verifies SBC solutions to ensure mathematical correctness
    and to prevent solver bugs from reaching the EA Web App submission layer.
    """
    @staticmethod
    def _check_requirements(squad: List[CanonicalPlayer], challenge: NormalizedChallenge, result: Dict[str, Any]):
        leagues = [p.league_id for p in squad if p.league_id is not None]
        nations = [p.nation_id for p in squad if p.nation_id is not None]
        clubs = [p.club_id for p in squad if p.club_id is not None]

        unique_leagues = len(set(leagues))
        unique_nations = len(set(nations))
        unique_clubs = len(set(clubs))

        league_counts = Counter(leagues)
        nation_counts = Counter(nations)
        club_counts = Counter(clubs)

        max_same_league = max(league_counts.values()) if league_counts else 0
        max_same_nation = max(nation_counts.values()) if nation_counts else 0
        max_same_club = max(club_counts.values()) if club_counts else 0

        rare_count = sum(1 for p in squad if p.is_rare)
        totw_count = sum(1 for p in squad if p.is_special)

        def check_scope(actual, req):
            if req.scope == "MIN" and actual < req.val:
                return False
            if req.scope == "MAX" and actual > req.val:
                return False
            if req.scope == "EXACT" and actual != req.val:
                return False
            return True

        for req in challenge.requirements:
            if req.req_type == "TEAM_RATING":
                if "team_rating" in result:
                    if not check_scope(result["team_rating"], req):
                        result["valid"] = False
                        result["errors"].append(f"Rating {result['team_rating']} fails {req.scope} {req.val}")

            elif req.req_type in ("MIN_TOTW", "SPECIAL"):
                if not check_scope(totw_count, req):
                    result["valid"] = False
                    result["errors"].append(f"Special cards {totw_count} fails {req.scope} {req.val}")

            elif req.req_type == "RARITY":
                if not check_scope(rare_count, req):
                    result["valid"] = False
                    result["errors"].append(f"Rare cards {rare_count} fails {req.scope} {req.val}")

            elif req.req_type == "MIN_CHEM":
                if "team_chemistry" in result:
                    if not check_scope(result["team_chemistry"], req):
                        result["valid"] = False
                        result["errors"].append(f"Chemistry {result['team_chemistry']} fails {req.scope} {req.val}")

            elif req.req_type == "LEAGUE_COUNT":
                if not check_scope(unique_leagues, req):
                    result["valid"] = False
                    result["errors"].append(f"League count {unique_leagues} fails {req.scope} {req.val}")

            elif req.req_type == "NATION_COUNT":
                if not check_scope(unique_nations, req):
                    result["valid"] = False
                    result["errors"].append(f"Nation count {unique_nations} fails {req.scope} {req.val}")

            elif req.req_type == "CLUB_COUNT":
                if not check_scope(unique_clubs, req):
                    result["valid"] = False
                    result["errors"].append(f"Club count {unique_clubs} fails {req.scope} {req.val}")

            elif req.req_type == "SAME_LEAGUE_COUNT":
                if not check_scope(max_same_league, req):
                    result["valid"] = False
                    result["errors"].append(f"Max same league {max_same_league} fails {req.scope} {req.val}")

            elif req.req_type == "SAME_NATION_COUNT":
                if not check_scope(max_same_nation, req):
                    result["valid"] = False
                    result["errors"].append(f"Max same nation {max_same_nation} fails {req.scope} {req.val}")

            elif req.req_type == "SAME_CLUB_COUNT":
                if not check_scope(max_same_club, req):
                    result["valid"] = False
                    result["errors"].append(f"Max same club {max_same_club} fails {req.scope} {req.val}")

    @staticmethod
    def verify_normal_squad(squad: List[CanonicalPlayer], challenge: NormalizedChallenge, inventory: List[CanonicalPlayer] = None) -> Dict[str, Any]:
        result = {
            "valid": True,
            "errors": [],
            "team_rating": 0,
            "team_chemistry": 0,
            "player_count": len(squad),
            "estimated_cost": sum(p.effective_cost for p in squad)
        }

        # Player count check
        if len(squad) != challenge.required_player_count:
            result["valid"] = False
            result["errors"].append(f"Invalid player count: {len(squad)} instead of {challenge.required_player_count}")

        # Unique Instance IDs
        instance_ids = [p.instance_id for p in squad if p.instance_id]
        if len(set(instance_ids)) != len(instance_ids):
            result["valid"] = False
            result["errors"].append("Duplicate instances found in solution.")
        unknown_definitions = [p.definition_id for p in squad if not p.instance_id]
        if len(set(unknown_definitions)) != len(unknown_definitions):
            result["valid"] = False
            result["errors"].append("Cannot distinguish repeated definitions without instance IDs.")
        if set(unknown_definitions) & {p.definition_id for p in squad if p.instance_id}:
            result["valid"] = False
            result["errors"].append("Cannot match unidentified card to a physical instance.")

        # Inventory check
        if inventory is not None:
            inventory_dict = {p.instance_id: p for p in inventory if p.instance_id}
            verified_squad = []
            for p in squad:
                if not p.instance_id or p.instance_id not in inventory_dict:
                    result["valid"] = False
                    result["errors"].append(f"Instance {p.instance_id} (Definition {p.definition_id}) not in inventory.")
                    verified_squad.append(p)
                else:
                    verified_squad.append(inventory_dict[p.instance_id])
            squad = verified_squad
            result["estimated_cost"] = sum(p.effective_cost for p in squad)

        # Rating calculation
        from .rating import calculate_team_rating
        result["team_rating"] = calculate_team_rating(squad)
        result["team_chemistry"] = calculate_chemistry(squad)
        if len(squad) != 11 and any(req.req_type == "TEAM_RATING" for req in challenge.requirements):
            result["valid"] = False
            result["errors"].append("EA-style rating is supported only for 11-player normal squads")

        # Requirements check
        IndependentVerifier._check_requirements(squad, challenge, result)

        return result

    @staticmethod
    def verify_streamlined_squad(squad: List[CanonicalPlayer], challenge: NormalizedChallenge, target_score: int, inventory: List[CanonicalPlayer] = None) -> Dict[str, Any]:
        result = {
            "valid": True,
            "errors": [],
            "total_score": 0,
            "required_score": target_score,
            "overshoot": 0,
            "player_count": len(squad),
            "estimated_cost": sum(p.effective_cost for p in squad)
        }

        # Streamlined squads usually don't need chemistry, but we include it if a req exists,
        # though it's typically score-based. We'll compute it lazily if needed, but for simplicity:
        result["team_chemistry"] = 0

        # Unique Instance IDs
        instance_ids = [p.instance_id for p in squad if p.instance_id]
        if len(set(instance_ids)) != len(instance_ids):
            result["valid"] = False
            result["errors"].append("Duplicate instances found in solution.")
        unknown_definitions = [p.definition_id for p in squad if not p.instance_id]
        if len(set(unknown_definitions)) != len(unknown_definitions):
            result["valid"] = False
            result["errors"].append("Cannot distinguish repeated definitions without instance IDs.")
        if set(unknown_definitions) & {p.definition_id for p in squad if p.instance_id}:
            result["valid"] = False
            result["errors"].append("Cannot match unidentified card to a physical instance.")

        # Inventory check
        if inventory is not None:
            inventory_dict = {p.instance_id: p for p in inventory if p.instance_id}
            verified_squad = []
            for p in squad:
                if not p.instance_id or p.instance_id not in inventory_dict:
                    result["valid"] = False
                    result["errors"].append(f"Instance {p.instance_id} (Definition {p.definition_id}) not in inventory.")
                    verified_squad.append(p)
                else:
                    verified_squad.append(inventory_dict[p.instance_id])
            squad = verified_squad
            result["estimated_cost"] = sum(p.effective_cost for p in squad)
        result["team_chemistry"] = calculate_chemistry(squad)

        # Score check
        total_score = sum(p.item_score for p in squad)
        result["total_score"] = total_score

        if total_score < target_score:
            result["valid"] = False
            result["errors"].append(f"Score {total_score} is below target {target_score}")
        else:
            result["overshoot"] = total_score - target_score

        # Player limit check
        domain_limit = challenge.max_player_count
        if domain_limit is None and challenge.required_player_count != 11:
            domain_limit = challenge.required_player_count
        if domain_limit is not None and len(squad) > domain_limit:
            result["valid"] = False
            result["errors"].append(f"Exceeded max player limit: {len(squad)} > {domain_limit}")
        if challenge.min_player_count is not None and len(squad) < challenge.min_player_count:
            result["valid"] = False
            result["errors"].append("Below minimum player count")

        # Requirements check
        IndependentVerifier._check_requirements(squad, challenge, result)

        return result
