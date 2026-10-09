from typing import List
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge
from app.services.sbc.solver_normal import CPNormalSolver
from app.services.sbc.solver_streamlined import CPStreamlinedSolver

class MultiCompletionEngine:
    def __init__(self, pool: List[CanonicalPlayer]):
        self.pool = pool

    def solve(self, challenge: NormalizedChallenge, num_completions: int = 1) -> List[List[CanonicalPlayer]]:
        completions = []
        current_pool = list(self.pool)
        
        for _ in range(num_completions):
            if not current_pool:
                break
                
            if challenge.type == "STREAMLINED":
                solver = CPStreamlinedSolver(current_pool)
            else:
                solver = CPNormalSolver(current_pool)
                
            result = solver.solve(challenge)
            
            if result:
                completions.append(result)
                # Remove used items from pool
                used_ids = {p.item_id for p in result}
                current_pool = [p for p in current_pool if p.item_id not in used_ids]
            else:
                break
                
        return completions
