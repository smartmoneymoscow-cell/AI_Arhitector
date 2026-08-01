"""
test_server.py — Backend API Tests (server.py monolith)

v6.0 — LLM-only парсинг. Regex удалён.
Тесты используют моки для LLM-вызовов.

Run: pytest tests/test_server.py -v
"""
import json
import pytest
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════
# VALIDATION TESTS (no LLM needed)
# ═══════════════════════════════════════════════════════════════

class TestValidation:
    """Тесты валидации параметров (без LLM)."""

    def test_validate_defaults(self):
        from shared.validation import validate_params
        result = validate_params({})
        assert result["object_type"] == "building"
        assert result["floors"] == 2
        assert result["width_m"] == 10

    def test_validate_room(self):
        from shared.validation import validate_params
        result = validate_params({"object_type": "room", "room_type": "bedroom"})
        assert result["object_type"] == "room"
        assert result["room_type"] == "bedroom"
        assert "bed" in result["furniture"]

    def test_validate_invalid_values(self):
        from shared.validation import validate_params
        result = validate_params({"object_type": "INVALID", "style": "INVALID"})
        assert result["object_type"] == "building"
        assert result["style"] == "modern"


# ═══════════════════════════════════════════════════════════════
# ROUTING TESTS (no LLM needed)
# ═══════════════════════════════════════════════════════════════

class TestRouting:
    """Тесты маршрутизации."""

    def test_building_type(self):
        from shared.parser import get_generation_type
        assert get_generation_type({"object_type": "building"}) == "building"

    def test_room_type(self):
        from shared.parser import get_generation_type
        assert get_generation_type({"object_type": "room"}) == "interior"

    def test_interior_type(self):
        from shared.parser import get_generation_type
        assert get_generation_type({"object_type": "interior"}) == "interior"


# ═══════════════════════════════════════════════════════════════
# PARSER TESTS (with mocks)
# ═══════════════════════════════════════════════════════════════

MOCK_RESPONSES = {
    "двухэтажный дом": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.5},
    "дом 10×12": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.8},
    "кирпичный дом": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "brick", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.7},
    "деревянный дом": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "wood", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.7},
    "дом с плоской кровлей": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster", "roof_type": "flat", "features": [], "furniture": [], "confidence": 0.7},
    "дом с двускатной кровлей": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.7},
    "офис 5 этажей стекло 20×24": {"object_type": "building", "building_type": "office", "floors": 5, "width_m": 20, "length_m": 24, "style": "modern", "material": "glass", "roof_type": "flat", "features": [], "furniture": [], "confidence": 0.95},
}


async def _mock_call_openrouter(model, prompt, timeout, api_key):
    text = prompt

    for key, resp in MOCK_RESPONSES.items():
        if key in text or text in key:
            return resp
    return {"object_type": "building", "building_type": "house", "floors": 2,
            "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster",
            "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.5}


class TestParser:
    """Тесты парсера с моками."""

    @patch("shared.parser._get_api_keys", return_value=["test-key"])
    @patch("shared.parser._call_openrouter", side_effect=_mock_call_openrouter)
    def test_parse_floors(self, mock_keys, mock):
        from shared.parser import parse_prompt
        params = parse_prompt("двухэтажный дом")
        assert params["floors"] == 2

    @patch("shared.parser._get_api_keys", return_value=["test-key"])
    @patch("shared.parser._call_openrouter", side_effect=_mock_call_openrouter)
    def test_parse_dimensions(self, mock_keys, mock):
        from shared.parser import parse_prompt
        params = parse_prompt("дом 10×12")
        assert params["width_m"] == 10
        assert params["length_m"] == 12

    @patch("shared.parser._get_api_keys", return_value=["test-key"])
    @patch("shared.parser._call_openrouter", side_effect=_mock_call_openrouter)
    def test_parse_material_brick(self, mock_keys, mock):
        from shared.parser import parse_prompt
        params = parse_prompt("кирпичный дом")
        assert params["material"] == "brick"

    @patch("shared.parser._get_api_keys", return_value=["test-key"])
    @patch("shared.parser._call_openrouter", side_effect=_mock_call_openrouter)
    def test_parse_material_wood(self, mock_keys, mock):
        from shared.parser import parse_prompt
        params = parse_prompt("деревянный дом")
        assert params["material"] == "wood"

    @patch("shared.parser._get_api_keys", return_value=["test-key"])
    @patch("shared.parser._call_openrouter", side_effect=_mock_call_openrouter)
    def test_parse_roof_flat(self, mock_keys, mock):
        from shared.parser import parse_prompt
        params = parse_prompt("дом с плоской кровлей")
        assert params["roof_type"] == "flat"

    @patch("shared.parser._get_api_keys", return_value=["test-key"])
    @patch("shared.parser._call_openrouter", side_effect=_mock_call_openrouter)
    def test_parse_roof_gabled(self, mock_keys, mock):
        from shared.parser import parse_prompt
        params = parse_prompt("дом с двускатной кровлей")
        assert params["roof_type"] == "gabled"

    @patch("shared.parser._get_api_keys", return_value=["test-key"])
    @patch("shared.parser._call_openrouter", side_effect=_mock_call_openrouter)
    def test_parse_office_glass(self, mock_keys, mock):
        from shared.parser import parse_prompt
        params = parse_prompt("офис 5 этажей стекло 20×24")
        assert params["floors"] == 5
        assert params["width_m"] == 20
        assert params["material"] == "glass"


# ═══════════════════════════════════════════════════════════════
# COMPILATION TESTS
# ═══════════════════════════════════════════════════════════════

class TestCompilation:
    """Тесты что файлы компилируются."""

    @pytest.mark.parametrize("path", [
        "server.py",
        "shared/parser.py",
        "shared/validation.py",
        "shared/config.py",
        "shared/models.py",
        "gateway/app.py",
        "llm-service/app.py",
        "blender-service/app.py",
    ])
    def test_compiles(self, path):
        import py_compile
        full = os.path.join(os.path.dirname(__file__), "..", path)
        py_compile.compile(full, doraise=True)


# ═══════════════════════════════════════════════════════════════
# NO REGEX TESTS
# ═══════════════════════════════════════════════════════════════

class TestNoRegex:
    """Тесты что regex удалён из production-кода."""

    def test_no_fallback_regex_in_parser(self):
        import shared.parser as p
        assert not hasattr(p, 'fallback_regex_parse')

    def test_no_regex_in_parser_source(self):
        source = open(os.path.join(os.path.dirname(__file__), "..", "shared", "parser.py")).read()
        assert "def fallback_regex_parse" not in source


# ═══════════════════════════════════════════════════════════════
# CACHE TESTS
# ═══════════════════════════════════════════════════════════════

class TestCache:
    """Тесты кеша."""

    def test_cache_stats(self):
        from shared.parser import get_cache_stats
        stats = get_cache_stats()
        assert "l1_entries" in stats
        assert "llm_cascade" in stats
        assert len(stats["llm_cascade"]) == 7
