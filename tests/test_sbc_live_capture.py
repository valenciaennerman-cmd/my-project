"""
Tests for the safe live-capture mechanism.
Verifies that PII/auth data is stripped and domain data is preserved.
"""
import json
import os
import tempfile
import pytest

from app.services.sbc.live_capture import (
    sanitize_dict,
    sanitize_headers,
    extract_challenge_fixture,
    extract_player_fixture,
    save_fixture,
    capture_validation_comparison,
)


class TestSanitizeDict:
    def test_strips_session_tokens(self):
        data = {"sid": "abc123", "name": "My Challenge", "sessionId": "xyz"}
        result = sanitize_dict(data)
        assert result["sid"] == "[REDACTED]"
        assert result["sessionId"] == "[REDACTED]"
        assert result["name"] == "My Challenge"

    def test_strips_account_data(self):
        data = {"personaId": "12345", "email": "test@test.com", "rating": 85}
        result = sanitize_dict(data)
        assert result["personaId"] == "[REDACTED]"
        assert result["email"] == "[REDACTED]"
        assert result["rating"] == 85

    def test_strips_nested_sensitive_data(self):
        data = {"player": {"name": "Messi", "accessToken": "secret123"}}
        result = sanitize_dict(data)
        assert result["player"]["name"] == "Messi"
        assert result["player"]["accessToken"] == "[REDACTED]"

    def test_strips_list_items(self):
        data = [{"sid": "abc"}, {"name": "OK"}]
        result = sanitize_dict(data)
        assert result[0]["sid"] == "[REDACTED]"
        assert result[1]["name"] == "OK"

    def test_catches_token_in_key_name(self):
        data = {"customAuthToken": "secret", "value": 42}
        result = sanitize_dict(data)
        assert result["customAuthToken"] == "[REDACTED]"
        assert result["value"] == 42

    def test_primitives_pass_through(self):
        assert sanitize_dict(42) == 42
        assert sanitize_dict("hello") == "hello"
        assert sanitize_dict(None) is None


class TestSanitizeHeaders:
    def test_strips_auth_headers(self):
        headers = {
            "Authorization": "Bearer xyz",
            "Cookie": "session=abc",
            "Content-Type": "application/json",
            "X-UT-SID": "ut-session-id",
        }
        result = sanitize_headers(headers)
        assert result["Authorization"] == "[REDACTED]"
        assert result["Cookie"] == "[REDACTED]"
        assert result["X-UT-SID"] == "[REDACTED]"
        assert result["Content-Type"] == "application/json"


class TestExtractChallengeFixture:
    def test_preserves_challenge_fields(self):
        raw = {
            "challengeId": "ch-001",
            "name": "85 Rated Squad",
            "type": "NORMAL",
            "formation": "4-3-3",
            "eligibilityRequirements": [{"type": "RATING", "value": 85}],
            "requiredPlayerCount": 11,
            "sid": "secret-session",
        }
        fixture = extract_challenge_fixture(raw)
        assert fixture["challenge_id"] == "ch-001"
        assert fixture["name"] == "85 Rated Squad"
        assert fixture["type"] == "NORMAL"
        assert fixture["_fc_version"] == "FC27"
        assert fixture["_confidence"] == "CAPTURED_UNVALIDATED"
        assert "secret-session" not in json.dumps(fixture)

    def test_recursive_redaction_and_determinism(self):
        raw = {"challengeId": "c1", "requirements": [{"type": "RATING", "value": 85,
               "nested": [{"ownerEmail": "person@example.com", "sessionToken": "secret"}]}],
               "account": {"personaId": "private"}}
        first = extract_challenge_fixture(raw)
        assert first == extract_challenge_fixture(raw)
        payload = json.dumps(first)
        assert "person@example.com" not in payload
        assert "secret" not in payload
        assert "private" not in payload

    def test_excessive_nesting_fails_closed(self):
        data = {"value": 1}
        for _ in range(52):
            data = {"nested": data}
        with pytest.raises(ValueError):
            sanitize_dict(data)


class TestExtractPlayerFixture:
    def test_preserves_player_fields(self):
        raw = {
            "definitionId": "12345",
            "name": "Messi",
            "rating": 93,
            "position": "RW",
            "leagueId": 53,
            "nationId": 52,
            "clubId": 241,
            "isIcon": False,
            "isHero": False,
            "personaId": "owner-123",
        }
        fixture = extract_player_fixture(raw)
        assert fixture["definition_id"] == "12345"
        assert fixture["name"] == "Messi"
        assert fixture["rating"] == 93
        assert "owner-123" not in json.dumps(fixture)


class TestSaveFixture:
    def test_saves_to_disk(self, tmp_path):
        fixture = {"test": "data", "_capture_version": "1.0"}
        path = save_fixture(fixture, "test", str(tmp_path))
        assert os.path.exists(path)
        with open(path) as f:
            loaded = json.load(f)
        assert loaded["test"] == "data"


class TestValidationComparison:
    def test_captures_rating_match(self, tmp_path):
        path = capture_validation_comparison(
            squad_ratings=[85, 85, 85, 85, 85, 85, 85, 85, 85, 85, 85],
            local_rating=85,
            ea_validation_rating=85,
            local_chemistry=33,
            ea_validation_chemistry=33,
            challenge_id="test-001",
            output_dir=str(tmp_path),
        )
        with open(path) as f:
            data = json.load(f)
        assert data["rating_match"] is True
        assert data["chemistry_match"] is True

    def test_captures_rating_mismatch(self, tmp_path):
        path = capture_validation_comparison(
            squad_ratings=[85] * 11,
            local_rating=85,
            ea_validation_rating=84,
            local_chemistry=30,
            ea_validation_chemistry=31,
            challenge_id="test-002",
            output_dir=str(tmp_path),
        )
        with open(path) as f:
            data = json.load(f)
        assert data["rating_match"] is False
        assert data["chemistry_match"] is False

    def test_handles_no_ea_response(self, tmp_path):
        path = capture_validation_comparison(
            squad_ratings=[85] * 11,
            local_rating=85,
            ea_validation_rating=None,
            local_chemistry=30,
            ea_validation_chemistry=None,
            challenge_id="test-003",
            output_dir=str(tmp_path),
        )
        with open(path) as f:
            data = json.load(f)
        assert data["rating_match"] is None
        assert data["chemistry_match"] is None
