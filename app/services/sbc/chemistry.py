from collections import defaultdict
from typing import List, Dict, Any

from app.services.sbc.models import CanonicalPlayer


# =========================================================================
# DOMAIN CONFIGURATION: Versioned Chemistry Rules
# =========================================================================
# Each version declares its rules and an `authoritative` flag.
# authoritative=True means the rules are confirmed against live EA data.
# authoritative=False means UNVERIFIED_DOMAIN_RULE — rules are inferred
# from prior versions and may not reflect actual FC27 behavior.
# =========================================================================

chemistry_rules_fc24 = {
    "version": "FC24",
    "authoritative": False,  # Local FC24-era reference; no live evidence in this repository
    "club_thresholds": {7: 3, 4: 2, 2: 1},
    "nation_thresholds": {8: 3, 5: 2, 2: 1},
    "league_thresholds": {8: 3, 5: 2, 3: 1},
    "icon_chem": 3,
    "hero_chem": 3,
    "icon_nation_weight": 2,   # Icons contribute 2× to nation chemistry pool
    "icon_league_weight": 1,   # Icons contribute to ALL league pools (via total_icons)
    "hero_league_weight": 2,   # Heroes contribute 2× to their league chemistry pool
    "hero_nation_weight": 1,   # Heroes contribute 1× to nation
    # UNVERIFIED_DOMAIN_RULE: Premium Chemistry, Radioactive, manager bonuses
    # not implemented — no live evidence for these modifiers
    "premium_chemistry": None,  # Not implemented
    "radioactive": None,        # Not implemented
    "managers": None,           # Not implemented
}

# UNVERIFIED_DOMAIN_RULE: FC27 rules lack live evidence.
# These are copied from FC24 and MUST NOT be marked authoritative
# until runtime/live capture confirms actual FC27 thresholds.
chemistry_rules_fc27 = {
    "version": "FC27",
    "authoritative": False,  # UNVERIFIED_DOMAIN_RULE
    "club_thresholds": {7: 3, 4: 2, 2: 1},
    "nation_thresholds": {8: 3, 5: 2, 2: 1},
    "league_thresholds": {8: 3, 5: 2, 3: 1},
    "icon_chem": 3,
    "hero_chem": 3,
    "icon_nation_weight": 2,
    "icon_league_weight": 1,
    "hero_league_weight": 2,
    "hero_nation_weight": 1,
    "premium_chemistry": None,
    "radioactive": None,
    "managers": None,
}

# Active rules — defaults to FC27 (unverified)
ACTIVE_CHEMISTRY_RULES = chemistry_rules_fc27


def get_rules_confidence(rules: Dict[str, Any]) -> str:
    """Returns the confidence level of the chemistry rules."""
    if rules.get("authoritative"):
        return f"VERIFIED_LIVE ({rules.get('version', 'unknown')})"
    source = "FC24-era thresholds" if rules.get("version") == "FC27" else "local reference rules"
    return f"UNVERIFIED_DOMAIN_RULE ({rules.get('version', 'unknown')} — {source})"


def _get_chem_from_thresholds(count: int, thresholds: Dict[int, int]) -> int:
    for threshold in sorted(thresholds.keys(), reverse=True):
        if count >= threshold:
            return thresholds[threshold]
    return 0

def calculate_chemistry(squad: List[CanonicalPlayer], rules: Dict[str, Any] = None) -> int:
    if rules is None:
        rules = ACTIVE_CHEMISTRY_RULES

    club_counts = defaultdict(int)
    nation_counts = defaultdict(int)
    league_counts = defaultdict(int)

    icon_count = 0

    for p in squad:
        if p.is_icon:
            icon_count += 1
            if p.nation_id is not None:
                nation_counts[p.nation_id] += rules.get("icon_nation_weight", 2)
            if p.club_id is not None:
                club_counts[p.club_id] += 1
        elif p.is_hero:
            if p.league_id is not None:
                league_counts[p.league_id] += rules.get("hero_league_weight", 2)
            if p.nation_id is not None:
                nation_counts[p.nation_id] += rules.get("hero_nation_weight", 1)
            if p.club_id is not None:
                club_counts[p.club_id] += 1
        else:
            if p.league_id is not None:
                league_counts[p.league_id] += 1
            if p.nation_id is not None:
                nation_counts[p.nation_id] += 1
            if p.club_id is not None:
                club_counts[p.club_id] += 1

    total_chem = 0
    for p in squad:
        if p.is_icon or p.is_hero:
            total_chem += rules.get("icon_chem", 3) if p.is_icon else rules.get("hero_chem", 3)
            continue

        p_chem = 0

        # Calculate club chem
        if p.club_id is not None:
            club_c = club_counts[p.club_id]
            p_chem += _get_chem_from_thresholds(club_c, rules["club_thresholds"])

        # Calculate nation chem
        if p.nation_id is not None:
            nation_c = nation_counts[p.nation_id]
            p_chem += _get_chem_from_thresholds(nation_c, rules["nation_thresholds"])

        # Calculate league chem — Icons contribute to ALL leagues
        if p.league_id is not None:
            league_c = league_counts[p.league_id] + icon_count * rules.get("icon_league_weight", 1)
            p_chem += _get_chem_from_thresholds(league_c, rules["league_thresholds"])

        total_chem += min(3, p_chem)

    return total_chem
