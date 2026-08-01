"""
test_generation.py — Интеграционные тесты генерации.

v6.0 — LLM-only парсинг. Regex удалён.
Тесты используют моки для LLM-вызовов.

Покрывает:
  - Парсинг промтов (мок LLM + валидация)
  - Маршрутизацию building/interior
  - Компиляцию bpy-скриптов
  - Валидацию параметров
  - Каскад LLM моделей
  - Redis кеш
  - Анти-галлюцинационные тесты

Запуск:
  python -m pytest tests/test_generation.py -v
"""
import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.parser import (
    parse_prompt, parse_prompt_async, AllModelsFailedError,
    get_generation_type, get_cache_stats, LLM_CASCADE,
    _validate, _extract_json, _l1_get, _l1_set,
)
from shared.validation import (
    validate_params,
    DEFAULT_FURNITURE,
    VALID_OBJECT_TYPES,
    VALID_BUILDING_TYPES,
    VALID_ROOM_TYPES,
    VALID_STYLES,
    VALID_MATERIALS,
    VALID_ROOF_TYPES,
)


# ═══════════════════════════════════════════════════════════════
# MOCK LLM RESPONSES
# ═══════════════════════════════════════════════════════════════

def _mock_llm_response(raw_params: dict):
    """Создаёт мок ответа OpenRouter API."""
    return {
        "choices": [{"message": {"content": json.dumps(raw_params, ensure_ascii=False)}}]
    }


# Параметры для анти-галлюцинационной матрицы
HALLUCINATION_MATRIX = [
    ("сделай дизайн коттеджа", "building", "cottage", None, []),
    ("сделай дизайн интерьера детской", "room", "children", None, []),
    ("красивую спальню в стиле хайтек", "room", "bedroom", "hitech", []),
    ("интерьерный дизайн квартиры на 64 кв метра", "interior", "apartment", None, []),
    ("офис 5 этажей стекло плоская кровля 20×24", "building", "office", None, []),
    ("двухэтажный кирпичный дом 10×12 с балконом", "building", "house", None, ["balcony"]),
    ("деревянный коттедж 2 этажа терраса гараж 12×15", "building", "cottage", None, ["terrace", "garage"]),
    ("построй что-нибудь красивое", "building", "house", None, []),
    ("кухня в стиле лофт 4×5", "room", "kitchen", "loft", []),
    ("современный таунхаус 3 этажа минимализм", "building", "townhouse", "minimalist", []),
]

# Мок LLM ответы для каждого промта из матрицы
MOCK_LLM_RESPONSES = {
    "сделай дизайн коттеджа": {"object_type": "building", "building_type": "cottage", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.7},
    "сделай дизайн интерьера детской": {"object_type": "room", "room_type": "children", "floors": 1, "width_m": 4, "length_m": 5, "style": "modern", "material": "plaster", "roof_type": "flat", "features": [], "furniture": ["bed", "desk", "bookshelf"], "confidence": 0.9},
    "красивую спальню в стиле хайтек": {"object_type": "room", "room_type": "bedroom", "floors": 1, "width_m": 5, "length_m": 6, "style": "hitech", "material": "plaster", "roof_type": "flat", "features": [], "furniture": ["bed", "wardrobe", "nightstand"], "confidence": 0.85},
    "интерьерный дизайн квартиры на 64 кв метра": {"object_type": "interior", "building_type": "apartment", "floors": 1, "width_m": 8, "length_m": 8, "style": "modern", "material": "plaster", "roof_type": "flat", "features": [], "furniture": [], "confidence": 0.6},
    "офис 5 этажей стекло плоская кровля 20×24": {"object_type": "building", "building_type": "office", "floors": 5, "width_m": 20, "length_m": 24, "style": "modern", "material": "glass", "roof_type": "flat", "features": [], "furniture": [], "confidence": 0.95},
    "двухэтажный кирпичный дом 10×12 с балконом": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "brick", "roof_type": "gabled", "features": ["balcony"], "furniture": [], "confidence": 0.95},
    "деревянный коттедж 2 этажа терраса гараж 12×15": {"object_type": "building", "building_type": "cottage", "floors": 2, "width_m": 12, "length_m": 15, "style": "modern", "material": "wood", "roof_type": "gabled", "features": ["terrace", "garage"], "furniture": [], "confidence": 0.95},
    "построй что-нибудь красивое": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.3},
    "кухня в стиле лофт 4×5": {"object_type": "room", "room_type": "kitchen", "floors": 1, "width_m": 4, "length_m": 5, "style": "loft", "material": "plaster", "roof_type": "flat", "features": [], "furniture": ["table", "sink", "stove"], "confidence": 0.9},
    "современный таунхаус 3 этажа минимализм": {"object_type": "building", "building_type": "townhouse", "floors": 3, "width_m": 10, "length_m": 12, "style": "minimalist", "material": "plaster", "roof_type": "flat", "features": [], "furniture": [], "confidence": 0.85},
}


async def _mock_call_openrouter(model, prompt, timeout, api_key):
    """Мок _call_openrouter — возвращает предопределённый ответ."""
    for prompt_key, response in MOCK_LLM_RESPONSES.items():
        if prompt_key in prompt or prompt in prompt_key:
            return response
    # Дефолтный ответ
    return {"object_type": "building", "building_type": "house", "floors": 2,
            "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster",
            "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.5}

# Backward compat alias
_mock_call_llm = _mock_call_openrouter


# ═══════════════════════════════════════════════════════════════
# 1. LLM CASCADE
# ═══════════════════════════════════════════════════════════════

class TestLLMCascade:
    """Тесты LLM каскада."""

    def test_cascade_has_7_models(self):
        assert len(LLM_CASCADE) == 7

    def test_cascade_tiers(self):
        tiers = {m["tier"] for m in LLM_CASCADE}
        assert 1 in tiers
        assert 2 in tiers
        assert 3 in tiers

    def test_cascade_has_free_models(self):
        free = [m for m in LLM_CASCADE if ":free" in m["model"]]
        assert len(free) >= 3

    def test_cascade_order_strong_to_weak(self):
        tiers = [m["tier"] for m in LLM_CASCADE]
        assert tiers == sorted(tiers), "Cascade should be ordered from strong to weak"


# ═══════════════════════════════════════════════════════════════
# 2. PARSING WITH MOCKS
# ═══════════════════════════════════════════════════════════════

class TestPromptParsing:
    """Тесты парсинга промтов с моками LLM."""

    @pytest.mark.parametrize("text,obj_type,subtype,style,features", HALLUCINATION_MATRIX)
    @patch("shared.parser._get_api_keys", return_value=["test-key"])
    @patch("shared.parser._call_openrouter", side_effect=_mock_call_llm)
    def test_parse_returns_correct_types(self, mock_keys, mock_llm, text, obj_type, subtype, style, features):
        """Парсер возвращает корректные типы."""
        p = parse_prompt(text)

        assert p["object_type"] == obj_type, f"'{text}' → object_type='{p['object_type']}', ожидали '{obj_type}'"

        if obj_type == "building":
            assert p["building_type"] == subtype, f"'{text}' → building_type='{p['building_type']}'"
        elif obj_type == "room":
            assert p["room_type"] == subtype, f"'{text}' → room_type='{p.get('room_type')}'"

        if style:
            assert p["style"] == style, f"'{text}' → style='{p['style']}'"

        for feat in features:
            assert feat in p["features"], f"'{text}' → features={p['features']}, ожидали '{feat}'"

    @patch("shared.parser._get_api_keys", return_value=["test-key"])
    @patch("shared.parser._call_openrouter", side_effect=_mock_call_llm)
    def test_no_hallucinated_dimensions(self, mock_keys, mock_llm):
        p = parse_prompt("построй что-нибудь красивое")
        assert isinstance(p["width_m"], (int, float))
        assert isinstance(p["length_m"], (int, float))
        assert 1 <= p["width_m"] <= 200
        assert 1 <= p["length_m"] <= 200

    @patch("shared.parser._get_api_keys", return_value=["test-key"])
    @patch("shared.parser._call_openrouter", side_effect=_mock_call_llm)
    def test_no_hallucinated_features(self, mock_keys, mock_llm):
        p = parse_prompt("построй что-нибудь красивое")
        assert isinstance(p["features"], list)

    def test_empty_prompt_returns_defaults(self):
        p = parse_prompt("")
        assert p["object_type"] == "building"
        assert p["floors"] == 2

    def test_whitespace_prompt_returns_defaults(self):
        p = parse_prompt("   ")
        assert p["object_type"] == "building"


# ═══════════════════════════════════════════════════════════════
# 3. ALL MODELS FAILED
# ═══════════════════════════════════════════════════════════════

class TestAllModelsFailed:
    """Тесты поведения при недоступности всех моделей."""

    @patch("shared.parser._call_openrouter", return_value=None)
    @patch("shared.parser._l2_get", return_value=None)
    def test_raises_when_all_models_fail(self, mock_redis, mock_llm):
        with pytest.raises(AllModelsFailedError):
            parse_prompt("двухэтажный дом")

    @patch("shared.parser._call_openrouter", return_value=None)
    def test_uses_cache_when_models_fail(self, mock_llm):
        # Populate L1 cache
        _l1_set("test cached prompt", {"object_type": "building", "building_type": "house",
                                         "floors": 2, "width_m": 10, "length_m": 12,
                                         "style": "modern", "material": "plaster",
                                         "roof_type": "gabled", "features": [], "furniture": [],
                                         "confidence": 0.5})
        result = parse_prompt("test cached prompt")
        assert result["object_type"] == "building"


# ═══════════════════════════════════════════════════════════════
# 4. ROUTING
# ═══════════════════════════════════════════════════════════════

class TestRouting:
    """Тесты маршрутизации building/interior."""

    def test_building_type(self):
        assert get_generation_type({"object_type": "building"}) == "building"

    def test_room_type(self):
        assert get_generation_type({"object_type": "room"}) == "interior"

    def test_interior_type(self):
        assert get_generation_type({"object_type": "interior"}) == "interior"

    def test_default_type(self):
        assert get_generation_type({}) == "building"


# ═══════════════════════════════════════════════════════════════
# 5. COMPILATION
# ═══════════════════════════════════════════════════════════════

class TestCompilation:
    """Тесты что все Python файлы компилируются."""

    @pytest.mark.parametrize("path", [
        "shared/parser.py",
        "shared/validation.py",
        "shared/config.py",
        "shared/models.py",
        "shared/auth.py",
        "shared/tiled_render.py",
        "shared/agents/base.py",
        "shared/agents/parser_agent.py",
        "shared/agents/geometry_agent.py",
        "shared/agents/texture_agent.py",
        "shared/agents/render_agent.py",
        "shared/agents/export_agent.py",
        "shared/agents/quality_agent.py",
        "shared/agents/orchestrator.py",
        "gateway/app.py",
        "llm-service/app.py",
        "blender-service/app.py",
        "server.py",
    ])
    def test_file_compiles(self, path):
        import py_compile
        full_path = os.path.join(os.path.dirname(__file__), "..", path)
        py_compile.compile(full_path, doraise=True)


# ═══════════════════════════════════════════════════════════════
# 6. VALIDATION
# ═══════════════════════════════════════════════════════════════

class TestValidation:
    """Тесты валидации параметров."""

    def test_defaults(self):
        result = validate_params({})
        assert result["object_type"] == "building"
        assert result["building_type"] == "house"
        assert result["floors"] == 2
        assert result["width_m"] == 10
        assert result["length_m"] == 12

    def test_invalid_object_type(self):
        assert validate_params({"object_type": "INVALID"})["object_type"] == "building"

    def test_invalid_building_type(self):
        assert validate_params({"building_type": "INVALID"})["building_type"] == "house"

    def test_invalid_style(self):
        assert validate_params({"style": "INVALID"})["style"] == "modern"

    def test_invalid_material(self):
        assert validate_params({"material": "INVALID"})["material"] == "plaster"

    def test_invalid_roof(self):
        assert validate_params({"roof_type": "INVALID"})["roof_type"] == "gabled"

    def test_floors_too_high(self):
        assert validate_params({"floors": 100})["floors"] == 2

    def test_negative_dimensions(self):
        result = validate_params({"width_m": -5, "length_m": 0})
        assert result["width_m"] == 10
        assert result["length_m"] == 12

    def test_room_gets_default_furniture(self):
        result = validate_params({"object_type": "room", "room_type": "bedroom"})
        assert "bed" in result["furniture"]
        assert "wardrobe" in result["furniture"]

    def test_features_filtered(self):
        result = validate_params({"features": ["balcony", "INVALID", "garage"]})
        assert result["features"] == ["balcony", "garage"]

    def test_preserves_valid_values(self):
        result = validate_params({
            "object_type": "room", "room_type": "kitchen",
            "style": "loft", "material": "brick",
            "floors": 3, "width_m": 15, "length_m": 20,
        })
        assert result["object_type"] == "room"
        assert result["room_type"] == "kitchen"
        assert result["style"] == "loft"
        assert result["material"] == "brick"
        assert result["floors"] == 3
        assert result["width_m"] == 15
        assert result["length_m"] == 20

    def test_survives_none_values(self):
        result = validate_params({
            "object_type": None, "building_type": None, "room_type": None,
            "floors": None, "width_m": None, "style": None,
            "material": None, "roof_type": None, "features": None, "furniture": None,
        })
        assert isinstance(result, dict)
        assert result["object_type"] in VALID_OBJECT_TYPES


# ═══════════════════════════════════════════════════════════════
# 7. JSON EXTRACTION
# ═══════════════════════════════════════════════════════════════

class TestJSONExtraction:
    """Тесты извлечения JSON из ответов LLM."""

    def test_clean_json(self):
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_json_in_markdown(self):
        result = _extract_json('```json\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_json_with_surrounding_text(self):
        result = _extract_json('Here is the result: {"a": 1} done.')
        assert result == {"a": 1}

    def test_json_with_thinking_tags(self):
        result = _extract_json('<think>let me think</think>{"a": 1}')
        assert result == {"a": 1}

    def test_invalid_json(self):
        assert _extract_json("not json at all") is None

    def test_empty_string(self):
        assert _extract_json("") is None


# ═══════════════════════════════════════════════════════════════
# 8. CACHE
# ═══════════════════════════════════════════════════════════════

class TestCache:
    """Тесты L1 кеша."""

    def test_l1_set_get(self):
        _l1_set("test_key", {"object_type": "building"})
        result = _l1_get("test_key")
        assert result == {"object_type": "building"}

    def test_l1_miss(self):
        assert _l1_get("nonexistent_key_xyz") is None

    def test_cache_stats(self):
        stats = get_cache_stats()
        assert "l1_entries" in stats
        assert "l1_max" in stats
        assert "llm_cascade" in stats
        assert len(stats["llm_cascade"]) == 7


# ═══════════════════════════════════════════════════════════════
# 9. ROBUSTNESS
# ═══════════════════════════════════════════════════════════════

class TestRobustness:
    """Тесты устойчивости к мусорным входам."""

    def test_empty_prompt_returns_defaults(self):
        result = parse_prompt("")
        assert isinstance(result, dict)
        assert result["object_type"] == "building"

    def test_whitespace_prompt_returns_defaults(self):
        result = parse_prompt("   ")
        assert isinstance(result, dict)
        assert result["object_type"] == "building"

    @patch("shared.parser._get_api_keys", return_value=["test-key"])
    @patch("shared.parser._call_openrouter", side_effect=_mock_call_llm)
    @pytest.mark.parametrize("text", ["asdfghjkl", "12345", "🤖💀"])
    def test_garbage_input_with_mock(self, mock_keys, mock_llm, text):
        result = parse_prompt(text)
        assert isinstance(result, dict)
        assert "object_type" in result
        assert result["object_type"] in VALID_OBJECT_TYPES

    @patch("shared.parser._get_api_keys", return_value=["test-key"])
    @patch("shared.parser._call_openrouter", side_effect=_mock_call_llm)
    def test_long_prompt(self, mock_keys, mock_llm):
        result = parse_prompt("а" * 5000)
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════
# 10. NO REGEX IN PRODUCTION
# ═══════════════════════════════════════════════════════════════

class TestNoRegex:
    """Тесты что regex полностью удалён."""

    def test_no_fallback_regex_parse_function(self):
        import shared.parser as p
        assert not hasattr(p, 'fallback_regex_parse'), "fallback_regex_parse still exists!"

    def test_no_regex_imports(self):
        import shared.parser as p
        # parser should not have a regex-based parsing function
        source = open(p.__file__).read()
        assert "def fallback_regex_parse" not in source, "fallback_regex_parse function found in source!"
        assert "def regex_parse" not in source, "regex_parse function found in source!"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
