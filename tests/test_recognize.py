"""Card readers: shared normalisation, and the Ollama backend with the network
mocked.

The capability check matters most: a text-only model (qwen3:30b-a3b) answers an
image request with HTTP 400, so the app has to say that in words at startup
rather than failing on the user's first screenshot.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.services.recognize.base import (
    SCHEMA_REQUIRED,
    CardReader,
    VisionError,
    to_reading,
)
from app.services.recognize.ollama_reader import OllamaCardReader
from app.services.recognize.registry import BUILDERS, build_reader

HOST = "http://localhost:11434"


def payload(**overrides) -> dict:
    base = {
        "is_card": True,
        "name": "Zinedine Zidane",
        "rating": 94,
        "position": "CAM",
        "card_type": "icon",
        "card_style_description": "white marble with gold, holographic sheen",
        "confidence": 0.92,
    }
    base.update(overrides)
    return base


def chat_response(data: dict) -> httpx.Response:
    return httpx.Response(200, json={"message": {"content": json.dumps(data)}})


class TestToReading:
    def test_happy_path(self):
        reading = to_reading(payload())
        assert reading.is_card
        assert reading.name == "Zinedine Zidane"
        assert reading.rating == 94
        assert reading.position == "CAM"
        assert reading.card_type == "icon"
        assert reading.confidence == pytest.approx(0.92)

    def test_not_a_card_clears_the_rest(self):
        reading = to_reading({"is_card": False, "card_style_description": "a menu"})
        assert not reading.is_card
        assert reading.name is None and reading.rating is None

    def test_bad_rating_is_dropped_not_kept(self):
        """A stat value misread as the rating must not survive."""
        assert to_reading(payload(rating=155)).rating is None
        assert to_reading(payload(rating="abc")).rating is None
        assert to_reading(payload(rating=None)).rating is None

    def test_position_is_normalised(self):
        assert to_reading(payload(position="cam")).position == "CAM"
        assert to_reading(payload(position="CAM++")).position == "CAM"
        # A small model answering "SMID" is not a position; better None than wrong.
        assert to_reading(payload(position="SMID")).position is None

    def test_unknown_card_type_becomes_none(self):
        assert to_reading(payload(card_type="unknown")).card_type is None
        assert to_reading(payload(card_type="")).card_type is None

    def test_confidence_is_clamped(self):
        assert to_reading(payload(confidence=5)).confidence == 1.0
        assert to_reading(payload(confidence=-2)).confidence == 0.0
        assert to_reading(payload(confidence="nope")).confidence == 0.0

    def test_blank_name_becomes_none(self):
        assert to_reading(payload(name="   ")).name is None

    def test_raw_payload_is_kept_for_debugging(self):
        data = payload()
        assert to_reading(data).raw == data


class TestOllamaCapabilityCheck:
    @respx.mock
    async def test_vision_model_passes(self):
        respx.post(f"{HOST}/api/show").mock(
            return_value=httpx.Response(200, json={"capabilities": ["completion", "vision", "tools"]})
        )
        reader = OllamaCardReader(HOST, "qwen3.5:0.8b")
        await reader.verify()
        await reader.aclose()

    @respx.mock
    async def test_text_only_model_is_rejected_with_its_capabilities(self):
        """qwen3:30b-a3b reports completion/tools/thinking -- no vision."""
        respx.post(f"{HOST}/api/show").mock(
            return_value=httpx.Response(
                200, json={"capabilities": ["completion", "tools", "thinking"]}
            )
        )
        reader = OllamaCardReader(HOST, "qwen3:30b-a3b")
        with pytest.raises(VisionError) as exc:
            await reader.verify()
        message = str(exc.value)
        assert "qwen3:30b-a3b" in message
        assert "goruntu okuyamiyor" in message
        assert "thinking" in message, "the message should show what it CAN do"
        await reader.aclose()

    @respx.mock
    async def test_model_with_no_capabilities_reported_is_rejected(self):
        respx.post(f"{HOST}/api/show").mock(return_value=httpx.Response(200, json={}))
        reader = OllamaCardReader(HOST, "qwen3.5:4b")
        with pytest.raises(VisionError, match="bildirilmedi"):
            await reader.verify()
        await reader.aclose()

    @respx.mock
    async def test_missing_model_suggests_pulling_it(self):
        respx.post(f"{HOST}/api/show").mock(return_value=httpx.Response(404))
        reader = OllamaCardReader(HOST, "qwen3-vl:8b")
        with pytest.raises(VisionError, match="ollama pull qwen3-vl:8b"):
            await reader.verify()
        await reader.aclose()

    @respx.mock
    async def test_ollama_not_running(self):
        respx.post(f"{HOST}/api/show").mock(side_effect=httpx.ConnectError("refused"))
        reader = OllamaCardReader(HOST, "qwen3.5:0.8b")
        with pytest.raises(VisionError, match="baglanilamadi"):
            await reader.verify()
        await reader.aclose()


class TestOllamaRead:
    @pytest.fixture()
    def card_png(self, tmp_path):
        from PIL import Image

        path = tmp_path / "card.png"
        Image.new("RGB", (150, 180), (200, 170, 60)).save(path)
        return path

    @respx.mock
    async def test_reads_a_card(self, card_png):
        respx.post(f"{HOST}/api/show").mock(
            return_value=httpx.Response(200, json={"capabilities": ["vision"]})
        )
        route = respx.post(f"{HOST}/api/chat").mock(return_value=chat_response(payload()))

        reader = OllamaCardReader(HOST, "qwen3.5:0.8b")
        reading = await reader.read(card_png)
        await reader.aclose()

        assert reading.rating == 94 and reading.position == "CAM"
        sent = json.loads(route.calls[0].request.content)
        assert sent["model"] == "qwen3.5:0.8b"
        assert sent["stream"] is False
        assert sent["think"] is False
        assert sent["messages"][1]["images"], "the image must actually be attached"
        assert sorted(sent["format"]["required"]) == sorted(SCHEMA_REQUIRED)

    @respx.mock
    async def test_thinking_flag_is_forwarded(self, card_png):
        respx.post(f"{HOST}/api/show").mock(
            return_value=httpx.Response(200, json={"capabilities": ["vision", "thinking"]})
        )
        route = respx.post(f"{HOST}/api/chat").mock(return_value=chat_response(payload()))

        reader = OllamaCardReader(HOST, "qwen3.5:0.8b", think=True)
        await reader.read(card_png)
        await reader.aclose()

        assert json.loads(route.calls[0].request.content)["think"] is True

    @respx.mock
    async def test_http_400_is_explained_as_a_vision_problem(self, card_png):
        respx.post(f"{HOST}/api/show").mock(
            return_value=httpx.Response(200, json={"capabilities": ["vision"]})
        )
        respx.post(f"{HOST}/api/chat").mock(return_value=httpx.Response(400, text="bad"))

        reader = OllamaCardReader(HOST, "qwen3.5:4b")
        with pytest.raises(VisionError, match="goruntu okuyamiyor"):
            await reader.read(card_png)
        await reader.aclose()

    @respx.mock
    async def test_non_json_answer_is_reported_not_swallowed(self, card_png):
        respx.post(f"{HOST}/api/show").mock(
            return_value=httpx.Response(200, json={"capabilities": ["vision"]})
        )
        respx.post(f"{HOST}/api/chat").mock(
            return_value=httpx.Response(200, json={"message": {"content": "I think it is Zidane"}})
        )

        reader = OllamaCardReader(HOST, "qwen3.5:0.8b")
        with pytest.raises(VisionError, match="JSON"):
            await reader.read(card_png)
        await reader.aclose()

    @respx.mock
    async def test_timeout_suggests_a_way_out(self, card_png):
        respx.post(f"{HOST}/api/show").mock(
            return_value=httpx.Response(200, json={"capabilities": ["vision"]})
        )
        respx.post(f"{HOST}/api/chat").mock(side_effect=httpx.ReadTimeout("slow"))

        reader = OllamaCardReader(HOST, "qwen3.5:0.8b")
        with pytest.raises(VisionError, match="OLLAMA_TIMEOUT"):
            await reader.read(card_png)
        await reader.aclose()

    @respx.mock
    async def test_capability_check_runs_once(self, card_png):
        show = respx.post(f"{HOST}/api/show").mock(
            return_value=httpx.Response(200, json={"capabilities": ["vision"]})
        )
        respx.post(f"{HOST}/api/chat").mock(return_value=chat_response(payload()))

        reader = OllamaCardReader(HOST, "qwen3.5:0.8b")
        await reader.read(card_png)
        await reader.read(card_png)
        await reader.aclose()

        assert show.call_count == 1


class TestRegistry:
    def test_known_backends(self):
        assert set(BUILDERS) == {"anthropic", "ollama"}

    def test_unknown_backend_fails_loudly(self):
        from app.core.config import Settings

        settings = Settings(VISION_BACKEND="gpt4")
        with pytest.raises(VisionError, match="Bilinmeyen VISION_BACKEND"):
            build_reader(settings)

    def test_ollama_backend_needs_no_api_key(self):
        from app.core.config import Settings

        settings = Settings(VISION_BACKEND="ollama", ANTHROPIC_API_KEY="")
        reader = build_reader(settings)
        assert isinstance(reader, CardReader)
        assert reader.name == "ollama"

    def test_anthropic_backend_without_a_key_says_so(self):
        from app.core.config import Settings

        settings = Settings(VISION_BACKEND="anthropic", ANTHROPIC_API_KEY="")
        with pytest.raises(VisionError, match="ANTHROPIC_API_KEY"):
            build_reader(settings)
