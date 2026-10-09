import pytest
from app.services.sbc.models import CanonicalPlayer, NormalizedChallenge, Requirement
from app.services.sbc.swap import SwapEngine
from app.services.sbc.repair import RepairEngine

def test_strict_ovr_match():
    # MUST reject if OVR is different
    p1 = CanonicalPlayer(definition_id="1", name="Player 1", rating=80)
    candidate = CanonicalPlayer(definition_id="2", name="Candidate", rating=81)

    squad = [p1]
    pool = [p1, candidate]
    challenge = NormalizedChallenge(
        challenge_id="c1",
        name="Test",
        required_player_count=1,
        requirements=[]
    )

    # Should reject because 81 != 80
    new_squad = SwapEngine.attempt_swap(squad, p1, candidate, challenge, pool)
    assert new_squad is None

def test_repair_minimizes_changes():
    # minimum-change repair optimization
    p1 = CanonicalPlayer(definition_id="1", name="P1", rating=80, is_special=True) # TOTW
    p2 = CanonicalPlayer(definition_id="2", name="P2", rating=80, is_special=False)
    p3 = CanonicalPlayer(definition_id="3", name="P3", rating=80, is_special=False)

    candidate = CanonicalPlayer(definition_id="c", name="Candidate", rating=80, is_special=False) # Not TOTW

    # Pool has multiple TOTW replacements. We want to replace only ONE card to fix TOTW requirement.
    r1 = CanonicalPlayer(definition_id="r1", name="R1", rating=80, is_special=True)
    r2 = CanonicalPlayer(definition_id="r2", name="R2", rating=80, is_special=True)

    squad = [p1, p2, p3]
    pool = [p1, p2, p3, candidate, r1, r2]

    challenge = NormalizedChallenge(
        challenge_id="c2",
        name="Test",
        required_player_count=3,
        requirements=[
            Requirement(req_type="MIN_TOTW", val=1, scope="MIN")
        ]
    )

    # Swap p1 with candidate. This breaks TOTW.
    # Repair engine should drop either p2 or p3, and bring in r1 or r2.
    # Total changes from new_squad [candidate, p2, p3] should be exactly 1 card swapped out.
    repaired_squad = SwapEngine.attempt_swap(squad, p1, candidate, challenge, pool)
    assert repaired_squad is not None

    definition_ids = set(p.definition_id for p in repaired_squad)
    assert "c" in definition_ids

    # Check changes: candidate is locked, so we evaluate the other 2 cards.
    # We started with p2, p3. One of them should be kept, one replaced by r1 or r2.
    kept_originals = definition_ids.intersection({"2", "3"})
    assert len(kept_originals) == 1, "Should keep exactly one original card to minimize changes"

def test_repair_chemistry_failure():
    # What if the swap makes the chemistry fail, but it can be repaired by swapping one other card?
    # Does the repair engine correctly find the minimum change?

    # Initial Squad: 3 players from same club (Club A) -> Chemistry is 3 each = 9 chem total (min 9)
    p1 = CanonicalPlayer(definition_id="1", name="P1", rating=80, club_id=1, nation_id=1, league_id=1)
    p2 = CanonicalPlayer(definition_id="2", name="P2", rating=80, club_id=1, nation_id=1, league_id=1)
    p3 = CanonicalPlayer(definition_id="3", name="P3", rating=80, club_id=1, nation_id=1, league_id=1)

    # Candidate is from Club B
    candidate = CanonicalPlayer(definition_id="c", name="Candidate", rating=80, club_id=2, nation_id=2, league_id=2)

    # To fix chem, we might need a replacement for p2 or p3 that gives chem to Candidate,
    # OR we just need a Hero/Icon that gives chem. Let's make r1 an Icon (3 chem to self).
    # Wait, club/nation/league points: 3 players from Club A give 7 points -> 3 chem each.
    # If we swap p1 with candidate:
    # Squad: Candidate(B), P2(A), P3(A).
    # P2, P3 are Club A -> 2 players -> 2 points -> 1 chem maybe? Wait, let's just make r1 an ICON.
    # Actually, the solver_normal constraints:
    # Club: 2 pts -> 1 chem. (2 threshold = 1 chem).
    # So P2(A) and P3(A) get 1 chem each. Total = 2 chem.
    # Candidate(B) has 0 points -> 0 chem.
    # Total chem = 2.
    # Target chem = 4.

    r1 = CanonicalPlayer(definition_id="r1", name="R1 Icon", rating=80, is_icon=True) # Icon gets 3 chem.
    # If we replace P3 with r1:
    # Squad: Candidate(B), P2(A), R1(Icon).
    # Candidate(B) -> 0 chem.
    # P2(A) -> 0 chem (only 1 player from Club A now).
    # R1(Icon) -> 3 chem.
    # Total = 3 chem. Target = 4. Not enough.

    # What if Candidate gets chem?
    r2 = CanonicalPlayer(definition_id="r2", name="R2", rating=80, club_id=2, nation_id=2, league_id=2)
    # Squad: Candidate(B), P2(A), R2(B).
    # B has 2 players -> 1 chem each. Total 2.
    # A has 1 player -> 0 chem.
    # Total chem = 2.

    # Let's make the requirement MIN_CHEM = 6.
    # Initial: 3 players from Club 1. Club 1 pts = 3 (threshold 2=1 chem). Nation 1 pts = 3 (threshold 2=1 chem). League 1 pts = 3 (threshold 3=1 chem). Total = 3 chem each * 3 = 9.

    # Let's use a simpler requirement: SAME_CLUB_COUNT = 3.
    # Initial: P1, P2, P3 all Club 1.
    # Candidate: Club 2.
    # R1: Club 2.
    # R2: Club 2.

    p1 = CanonicalPlayer(definition_id="1", name="P1", rating=80, club_id=1)
    p2 = CanonicalPlayer(definition_id="2", name="P2", rating=80, club_id=1)
    p3 = CanonicalPlayer(definition_id="3", name="P3", rating=80, club_id=1)

    candidate = CanonicalPlayer(definition_id="c", name="C", rating=80, club_id=2)

    r1 = CanonicalPlayer(definition_id="r1", name="R1", rating=80, club_id=2)
    r2 = CanonicalPlayer(definition_id="r2", name="R2", rating=80, club_id=2)

    squad = [p1, p2, p3]
    pool = [p1, p2, p3, candidate, r1, r2]

    challenge = NormalizedChallenge(
        challenge_id="c3",
        name="Test Chem/Club",
        required_player_count=3,
        requirements=[
            Requirement(req_type="SAME_CLUB_COUNT", val=3, scope="MIN")
        ]
    )

    # Swap p1 with candidate.
    # Squad becomes [c(Club 2), p2(Club 1), p3(Club 1)]. Fails SAME_CLUB_COUNT=3.
    # Repair engine should drop p2, p3 and add r1, r2.
    repaired_squad = SwapEngine.attempt_swap(squad, p1, candidate, challenge, pool)
    assert repaired_squad is not None

    definition_ids = set(p.definition_id for p in repaired_squad)
    assert "c" in definition_ids
    assert "r1" in definition_ids
    assert "r2" in definition_ids
