from typing import List, Optional, Set, Any, Dict
from pydantic import BaseModel, Field
from enum import Enum
import math


class SolverStatus(str, Enum):
    """
    Precise CP-SAT outcome semantics.
    OPTIMAL: Proven optimal solution found.
    FEASIBLE: A feasible (but not necessarily optimal) solution found.
    INFEASIBLE: Proven infeasible — no valid solution exists.
    SEARCH_LIMIT_REACHED: Solver stopped due to time/resource bounds
        without proving feasibility or infeasibility. This is NOT the
        same as INFEASIBLE.
    ERROR: Solver encountered an internal error.
    """
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    SEARCH_LIMIT_REACHED = "SEARCH_LIMIT_REACHED"
    ERROR = "ERROR"


class SolverResult(BaseModel):
    """Structured result from any SBC solver."""
    status: SolverStatus
    squad: List["CanonicalPlayer"] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)

    @property
    def search_truncated(self) -> bool:
        return self.metadata.get("search_truncated", False)

    @property
    def solver_candidate_limit(self) -> Optional[int]:
        return self.metadata.get("solver_candidate_limit")

class CanonicalPlayer(BaseModel):
    definition_id: str
    instance_id: Optional[str] = None
    name: str
    rating: int
    is_rare: bool = False
    is_special: bool = False
    is_icon: bool = False
    is_hero: bool = False

    league_id: Optional[int] = None
    nation_id: Optional[int] = None
    club_id: Optional[int] = None

    preferred_position: Optional[str] = None
    possible_positions: List[str] = Field(default_factory=list)

    tradeable: bool = False
    storage: bool = False
    unassigned: bool = False
    duplicate: bool = False

    locked: bool = False
    excluded: bool = False
    prefer_untradeable: bool = True

    market_price: int = 0
    item_score: int = 0

    source: str = "club"
    is_concept: bool = False

    @property
    def effective_cost(self) -> int:
        if self.is_concept:
            return self.market_price

        cost = 0
        if self.tradeable:
            cost += self.market_price
        else:
            if self.prefer_untradeable:
                cost += int(self.market_price * 0.1) # Untradeable opportunity cost
            else:
                cost += self.market_price

        if self.storage:
            cost -= 100
        if self.unassigned or self.duplicate:
            cost -= 500
        if self.excluded:
            cost += 99999999

        return max(0, cost)

class Requirement(BaseModel):
    req_type: str # e.g., "TEAM_RATING", "MIN_CHEM", "MIN_TOTW"
    val: int
    scope: str = "MIN" # MIN, MAX, EXACT

class NormalizedChallenge(BaseModel):
    challenge_id: str
    name: str
    type: str = "NORMAL" # NORMAL or STREAMLINED
    required_player_count: int = 11
    min_player_count: Optional[int] = None
    max_player_count: Optional[int] = None
    requirements: List[Requirement] = Field(default_factory=list)
    score_requirement: Optional[int] = None
    submitted_score: Optional[int] = 0
