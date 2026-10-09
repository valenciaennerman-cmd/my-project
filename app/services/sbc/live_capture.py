"""
Safe fixture-capture mechanism for live authorized EA data.

Captures challenge requirements and card metadata needed for SBC math,
while stripping all authentication and personally identifiable data.

SAFETY RULES:
- Removes session tokens
- Removes cookies
- Removes authentication headers
- Removes account-identifying data (persona ID, nucleus ID, email)
- Preserves challenge requirements
- Preserves card metadata needed for SBC math
- Preserves chemistry-relevant fields
"""
import json
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


# Fields to strip from raw EA API responses
SENSITIVE_FIELDS = {
    # Authentication / session
    "sid", "pidId", "sessionId", "authCode", "accessToken",
    "refreshToken", "token", "cookie", "cookies",
    # Account identification
    "personaId", "nucleusId", "email", "userId",
    "displayName", "gamertag", "psnId", "xboxGamertag",
    # Network
    "ipAddress", "ip", "remoteAddr",
    # Internal EA fields
    "sku", "skuId",
}

# Headers to strip from captured requests
SENSITIVE_HEADERS = {
    "authorization", "cookie", "set-cookie",
    "x-ut-sid", "x-ut-phishing-token",
    "x-ut-route", "x-ut-embed-error",
}


def sanitize_dict(data: Any, depth: int = 0) -> Any:
    """
    Recursively sanitize a dictionary, removing sensitive fields.
    Returns a deep copy with sensitive data replaced by '[REDACTED]'.
    """
    if depth > 50:
        raise ValueError("Capture nesting exceeds safe limit")

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            key_lower = key.lower()
            if key_lower in {f.lower() for f in SENSITIVE_FIELDS}:
                result[key] = "[REDACTED]"
            elif any(h in key_lower for h in ("token", "session", "auth", "cookie", "password", "account", "persona", "nucleus", "secret", "email", "phone", "address", "gamertag", "owner", "profile", "device")):
                result[key] = "[REDACTED]"
            else:
                result[key] = sanitize_dict(value, depth + 1)
        return result
    elif isinstance(data, list):
        return [sanitize_dict(item, depth + 1) for item in data]
    elif isinstance(data, str) and re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", data):
        return "[REDACTED]"
    else:
        return data


def sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Strip authentication and session headers."""
    result = {}
    for key, value in headers.items():
        result[key] = "[REDACTED]" if key.lower() in SENSITIVE_HEADERS or any(
            term in key.lower() for term in ("auth", "token", "session", "cookie", "secret", "account")
        ) else sanitize_dict(value)
    return result


def extract_challenge_fixture(raw_challenge_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract a sanitized challenge fixture from raw EA challenge data.
    Preserves: requirements, formation, player count, score targets.
    Strips: session info, account data.
    """
    sanitized = sanitize_dict(raw_challenge_data)

    fixture = {
        "_capture_version": "1.0",
        "_fc_version": "FC27",
        "_confidence": "CAPTURED_UNVALIDATED",
        "challenge_id": sanitized.get("challengeId") or sanitized.get("id"),
        "name": sanitized.get("name") or sanitized.get("description"),
        "type": sanitized.get("type"),
        "formation": sanitized.get("formation"),
        "requirements": sanitized.get("eligibilityRequirements") or sanitized.get("requirements", []),
        "score_requirement": sanitized.get("scoreRequirement") or sanitized.get("targetScore"),
        "required_player_count": sanitized.get("requiredPlayerCount"),
        "min_player_count": sanitized.get("minPlayerCount"),
        "max_player_count": sanitized.get("maxPlayerCount"),
    }
    return fixture


def extract_player_fixture(raw_player_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract a sanitized player card fixture from raw EA player data.
    Preserves: rating, position, league, nation, club, rarity, chemistry-relevant traits.
    Strips: owner info, acquisition data.
    """
    sanitized = sanitize_dict(raw_player_data)

    fixture = {
        "_capture_version": "1.0",
        "_fc_version": "FC27",
        "definition_id": sanitized.get("definitionId") or sanitized.get("assetId") or sanitized.get("id"),
        "name": sanitized.get("name") or sanitized.get("commonName") or sanitized.get("lastName"),
        "rating": sanitized.get("rating") or sanitized.get("overallRating"),
        "position": sanitized.get("position") or sanitized.get("preferredPosition"),
        "league_id": sanitized.get("leagueId") or sanitized.get("league"),
        "league_name": sanitized.get("leagueName"),
        "nation_id": sanitized.get("nationId") or sanitized.get("nation"),
        "nation_name": sanitized.get("nationName"),
        "club_id": sanitized.get("clubId") or sanitized.get("club"),
        "club_name": sanitized.get("clubName"),
        "rarity": sanitized.get("rareflag") or sanitized.get("rarity"),
        "rarity_name": sanitized.get("rarityName"),
        "is_icon": sanitized.get("isIcon", False),
        "is_hero": sanitized.get("isHero", False),
        "item_score": sanitized.get("itemScore") or sanitized.get("discardValue"),
        "chemistry_style": sanitized.get("chemistryStyle"),
        "promo_type": sanitized.get("promoType"),
        "is_premium_chemistry": sanitized.get("isPremiumChemistry"),
        "is_radioactive": sanitized.get("isRadioactive"),
    }
    return fixture


def save_fixture(fixture: Dict[str, Any], fixture_type: str, output_dir: str = "fixtures/live_captures") -> str:
    """
    Save a sanitized fixture to disk with a unique filename.
    Returns the path to the saved fixture.
    """
    fixture = sanitize_dict(fixture)
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", fixture_type):
        raise ValueError("Invalid fixture type")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    content_hash = hashlib.sha256(json.dumps(fixture, sort_keys=True).encode()).hexdigest()[:12]
    filename = f"{fixture_type}_{content_hash}.json"

    filepath = output_path / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(fixture, f, indent=2, ensure_ascii=False)

    return str(filepath)


def capture_challenge(raw_data: Dict[str, Any], output_dir: str = "fixtures/live_captures") -> str:
    """Capture and save a sanitized challenge fixture."""
    fixture = extract_challenge_fixture(raw_data)
    return save_fixture(fixture, "challenge", output_dir)


def capture_player(raw_data: Dict[str, Any], output_dir: str = "fixtures/live_captures") -> str:
    """Capture and save a sanitized player fixture."""
    fixture = extract_player_fixture(raw_data)
    return save_fixture(fixture, "player", output_dir)


def capture_validation_comparison(
    squad_ratings: List[int],
    local_rating: int,
    ea_validation_rating: Optional[int],
    local_chemistry: int,
    ea_validation_chemistry: Optional[int],
    challenge_id: str,
    output_dir: str = "fixtures/live_captures"
) -> str:
    """
    Capture a rating/chemistry comparison between local calculation and EA validation.
    NON-DESTRUCTIVE — does not submit the SBC.

    The EA validation rating/chemistry comes from the pre-submission validation
    response that EA provides before actual submission.
    """
    fixture = {
        "_capture_version": "1.0",
        "_fc_version": "FC27",
        "_type": "validation_comparison",
        "challenge_id": sanitize_dict(challenge_id),
        "squad_ratings": squad_ratings,
        "local_rating": local_rating,
        "ea_validation_rating": ea_validation_rating,
        "rating_match": local_rating == ea_validation_rating if ea_validation_rating is not None else None,
        "local_chemistry": local_chemistry,
        "ea_validation_chemistry": ea_validation_chemistry,
        "chemistry_match": local_chemistry == ea_validation_chemistry if ea_validation_chemistry is not None else None,
    }
    return save_fixture(fixture, "validation_comparison", output_dir)
