from typing import List, Optional
from .models import CanonicalPlayer, NormalizedChallenge
from .verifier import IndependentVerifier
from .repair import RepairEngine

class SwapEngine:
    @staticmethod
    def attempt_swap(
        current_squad: List[CanonicalPlayer],
        original: CanonicalPlayer,
        candidate: CanonicalPlayer,
        challenge: NormalizedChallenge,
        pool: List[CanonicalPlayer]
    ) -> Optional[List[CanonicalPlayer]]:
        """
        Attempts to replace `original` with `candidate`.
        STRICT RULE: candidate.rating == original.rating.
        If the resulting squad is invalid, invokes RepairEngine to fix it
        by changing the minimum number of other unlocked items.
        """
        if original.rating != candidate.rating:
            return None # Must have exact same rating

        # Create new squad
        new_squad = []
        replaced = False
        for p in current_squad:
            match = False
            if p.instance_id and original.instance_id:
                match = (p.instance_id == original.instance_id)
            else:
                match = (p.definition_id == original.definition_id)

            if match and not replaced:
                new_squad.append(candidate)
                replaced = True
            else:
                new_squad.append(p)

        if not replaced:
            return None # Original player not found in current squad

        # Determine challenge type
        is_streamlined = getattr(challenge, "type", "NORMAL") == "STREAMLINED"

        # Verify the new squad
        if is_streamlined:
            target_score = challenge.score_requirement or 0
            verification = IndependentVerifier.verify_streamlined_squad(new_squad, challenge, target_score)
        else:
            verification = IndependentVerifier.verify_normal_squad(new_squad, challenge)

        if verification["valid"]:
            return new_squad

        # If invalid, try to repair
        # The swapped candidate is now locked, as well as any other already locked items
        locked_definition_ids = [p.instance_id or p.definition_id for p in new_squad if p.locked]
        if (candidate.instance_id or candidate.definition_id) not in locked_definition_ids:
            locked_definition_ids.append(candidate.instance_id or candidate.definition_id)

        # Exclude the original item from the pool so we don't bring it right back
        repair_pool = [p for p in pool if (p.instance_id or p.definition_id) != (original.instance_id or original.definition_id)]

        repaired_squad = RepairEngine.repair_squad(
            current_squad=new_squad,
            challenge=challenge,
            pool=repair_pool,
            locked_definition_ids=locked_definition_ids,
            is_streamlined=is_streamlined
        )
        return repaired_squad
