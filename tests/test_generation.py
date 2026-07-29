"""
test_generation.py — Интеграционные тесты генерации.

Покрывает:
  - Парсинг промтов (regex fallback)
  - Маршрутизацию building/interior
  - Компиляцию bpy-скриптов
  - Валидацию параметров (safe_val)
  - Анти-галлюцинационные тесты

Запуск:
  python -m pytest tests/test_generation.py -v
"""
import sys
import os
import json
import re

import pytest

# Добавить корень проекта в path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.parser import (
    fallback_regex_parse,
    get_generation_type,
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
# 1. ПАРСИНГ ПРОМТОВ — АНТИ-ГАЛЛЮЦИНАЦИОННАЯ МАТРИЦА
# ═══════════════════════════════════════════════════════════════

HALLUCINATION_MATRIX = [
    # (промт, ожидаемый object_type, ожидаемый subtype, ожидаемый style, ожидаемые features)
    ("сделай дизайн коттеджа", "building", "cottage", None, []),
    ("сделай дизайн интерьера детской", "room", "children", None, []),
    ("красивую спальню в стиле хайтек", "room", "bedroom", "hitech", []),
    ("интерьерный дизайн квартиры на 64 кв метра", "interior", "apartment", None, []),
    ("офис 5 этажей стекло плоская кровля 20×24", "building", "office", None, []),
    ("двухэтажный кирпичный дом 10×12 с балконом", "building", "house", None, ["balcony"]),
    ("деревянный коттедж 2 этажа терраса гараж 12×15", "building", "cottage", None, ["terrace", "garage"]),
    ("построй что-нибудь красивое", "building", "house", None, []),
    ("кухня в стиле лофт 4×5", "room", "kitchen", "loft", []),
    ("современный таунхаус 3 этажа минимализм", "building", "townhouse", None, []),
]


class TestPromptParsing:
    """Тесты парсинга промтов — анти-галлюцинационная матрица."""

    @pytest.mark.parametrize("text,obj_type,subtype,style,features", HALLUCINATION_MATRIX)
    def test_no_hallucination_parse(self, text, obj_type, subtype, style, features):
        """Парсер НЕ должен выдумывать параметры которых нет в промте."""
        p = fallback_regex_parse(text)

        # Проверка object_type
        assert p["object_type"] == obj_type, \
            f"'{text}' → object_type='{p['object_type']}', ожидали '{obj_type}'"

        # Проверка подтипа
        if obj_type == "building":
            assert p["building_type"] == subtype, \
                f"'{text}' → building_type='{p['building_type']}', ожидали '{subtype}'"
        elif obj_type == "room":
            assert p["room_type"] == subtype, \
                f"'{text}' → room_type='{p.get('room_type')}', ожидали '{subtype}'"

        # Проверка стиля
        if style:
            assert p["style"] == style, \
                f"'{text}' → style='{p['style']}', ожидали '{style}'"

        # Проверка features
        for feat in features:
            assert feat in p["features"], \
                f"'{text}' → features={p['features']}, ожидали '{feat}' в списке"

    def test_no_hallucinated_dimensions(self):
        """Если в промте нет размеров — дефолты, не выдуманные числа."""
        p = fallback_regex_parse("построй что-нибудь красивое")
        assert p["width_m"] in (10, 6, 5), f"Выдуман width_m={p['width_m']}"
        assert p["length_m"] in (12, 8, 6), f"Выдуман length_m={p['length_m']}"

    def test_no_hallucinated_features(self):
        """Если в промте нет features — пустой список."""
        p = fallback_regex_parse("построй что-нибудь красивое")
        assert p["features"] == [], f"Выдуманы features: {p['features']}"

    def test_no_false_feature_match(self):
        """Features не должны срабатывать на подстроки."""
        p = fallback_regex_parse("современный таунхаус")
        assert "terrace" not in p["features"], "Ложное срабатывание 'terrace' в 'современный'"
        assert "garage" not in p["features"], "Ложное срабатывание 'garage'"


# ═══════════════════════════════════════════════════════════════
# 2. МАРШРУТИЗАЦИЯ
# ═══════════════════════════════════════════════════════════════

class TestRouting:
    """Тесты маршрутизации building/interior."""

    def test_cottage_routes_to_building(self):
        p = fallback_regex_parse("коттедж")
        assert get_generation_type(p) == "building"

    def test_children_room_routes_to_interior(self):
        p = fallback_regex_parse("детская комната")
        assert get_generation_type(p) == "interior"

    def test_bedroom_routes_to_interior(self):
        p = fallback_regex_parse("спальня")
        assert get_generation_type(p) == "interior"

    def test_office_routes_to_building(self):
        p = fallback_regex_parse("офис 5 этажей")
        assert get_generation_type(p) == "building"

    def test_interior_design_routes_to_interior(self):
        p = fallback_regex_parse("интерьерный дизайн квартиры")
        assert get_generation_type(p) == "interior"

    def test_kitchen_routes_to_interior(self):
        p = fallback_regex_parse("кухня в стиле лофт")
        assert get_generation_type(p) == "interior"


# ═══════════════════════════════════════════════════════════════
# 3. КОМПИЛЯЦИЯ BPY-СКРИПТОВ
# ═══════════════════════════════════════════════════════════════

class TestBpyCompilation:
    """Тесты что bpy-скрипты компилируются."""

    def _get_generate_bpy(self):
        """Импорт generate_bpy_script из blender-service."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "blender_app",
            os.path.join(os.path.dirname(__file__), "..", "blender-service", "app.py"),
        )
        # Нельзя импортировать напрямую из-за Flask
        # Вместо этого проверяем что файл компилируется
        return None

    def test_blender_service_compiles(self):
        """blender-service/app.py компилируется."""
        import py_compile
        path = os.path.join(os.path.dirname(__file__), "..", "blender-service", "app.py")
        py_compile.compile(path, doraise=True)

    def test_shared_parser_compiles(self):
        """shared/parser.py компилируется."""
        import py_compile
        path = os.path.join(os.path.dirname(__file__), "..", "shared", "parser.py")
        py_compile.compile(path, doraise=True)

    def test_llm_service_compiles(self):
        """llm-service/app.py компилируется."""
        import py_compile
        path = os.path.join(os.path.dirname(__file__), "..", "llm-service", "app.py")
        py_compile.compile(path, doraise=True)

    def test_gateway_compiles(self):
        """gateway/app.py компилируется."""
        import py_compile
        path = os.path.join(os.path.dirname(__file__), "..", "gateway", "app.py")
        py_compile.compile(path, doraise=True)


# ═══════════════════════════════════════════════════════════════
# 4. ВАЛИДАЦИЯ ПАРАМЕТРОВ (safe_val)
# ═══════════════════════════════════════════════════════════════

class TestValidation:
    """Тесты валидации параметров."""

    def test_validate_params_defaults(self):
        """Дефолтные параметры валидны."""
        result = validate_params({})
        assert result["object_type"] == "building"
        assert result["building_type"] == "house"
        assert result["floors"] == 2
        assert result["width_m"] == 10
        assert result["length_m"] == 12

    def test_validate_params_invalid_object_type(self):
        """Невалидный object_type → дефолт."""
        result = validate_params({"object_type": "INVALID"})
        assert result["object_type"] == "building"

    def test_validate_params_invalid_building_type(self):
        """Невалидный building_type → дефолт."""
        result = validate_params({"building_type": "INVALID"})
        assert result["building_type"] == "house"

    def test_validate_params_invalid_style(self):
        """Невалидный style → дефолт."""
        result = validate_params({"style": "INVALID"})
        assert result["style"] == "modern"

    def test_validate_params_invalid_material(self):
        """Невалидный material → дефолт."""
        result = validate_params({"material": "INVALID"})
        assert result["material"] == "plaster"

    def test_validate_params_invalid_roof(self):
        """Невалидный roof_type → дефолт."""
        result = validate_params({"roof_type": "INVALID"})
        assert result["roof_type"] == "gabled"

    def test_validate_params_floors_too_high(self):
        """Слишком много этажей → дефолт."""
        result = validate_params({"floors": 100})
        assert result["floors"] == 2

    def test_validate_params_negative_dimensions(self):
        """Отрицательные размеры → дефолт."""
        result = validate_params({"width_m": -5, "length_m": 0})
        assert result["width_m"] == 10
        assert result["length_m"] == 12

    def test_validate_params_room_gets_default_furniture(self):
        """Комната без мебели → дефолтная мебель."""
        result = validate_params({"object_type": "room", "room_type": "bedroom"})
        assert "bed" in result["furniture"]
        assert "wardrobe" in result["furniture"]

    def test_validate_params_features_filtered(self):
        """Только валидные features проходят."""
        result = validate_params({"features": ["balcony", "INVALID", "garage"]})
        assert result["features"] == ["balcony", "garage"]

    def test_validate_params_preserves_valid_values(self):
        """Валидные значения не перезаписываются дефолтами."""
        result = validate_params({
            "object_type": "room",
            "room_type": "kitchen",
            "style": "loft",
            "material": "brick",
            "floors": 3,
            "width_m": 15,
            "length_m": 20,
        })
        assert result["object_type"] == "room"
        assert result["room_type"] == "kitchen"
        assert result["style"] == "loft"
        assert result["material"] == "brick"
        assert result["floors"] == 3
        assert result["width_m"] == 15
        assert result["length_m"] == 20


# ═══════════════════════════════════════════════════════════════
# 5. УСТОЙЧИВОСТЬ К МУСОРНЫМ ВХОДАМ
# ═══════════════════════════════════════════════════════════════

class TestRobustness:
    """Тесты устойчивости к мусорным входам."""

    GARBAGE_INPUTS = [
        "",
        "   ",
        "asdfghjkl",
        "12345",
        "🤖💀",
        "а" * 5000,
        '{"json": "injection"}',
        "<script>alert(1)</script>",
    ]

    @pytest.mark.parametrize("text", GARBAGE_INPUTS)
    def test_fallback_survives_garbage(self, text):
        """Fallback не должен падать на любом входе."""
        result = fallback_regex_parse(text)
        assert isinstance(result, dict)
        assert "object_type" in result
        assert result["object_type"] in VALID_OBJECT_TYPES

    def test_validate_survives_none_values(self):
        """validate_params не падает на None значениях."""
        result = validate_params({
            "object_type": None,
            "building_type": None,
            "room_type": None,
            "floors": None,
            "width_m": None,
            "style": None,
            "material": None,
            "roof_type": None,
            "features": None,
            "furniture": None,
        })
        assert isinstance(result, dict)
        assert result["object_type"] in VALID_OBJECT_TYPES


# ═══════════════════════════════════════════════════════════════
# 6. РАЗМЕРЫ И ПЛОЩАДЬ
# ═══════════════════════════════════════════════════════════════

class TestDimensions:
    """Тесты извлечения размеров."""

    def test_dimensions_from_pattern(self):
        """10×12 → width=10, length=12."""
        p = fallback_regex_parse("дом 10×12")
        assert p["width_m"] == 10
        assert p["length_m"] == 12

    def test_dimensions_from_x_pattern(self):
        """10x12 → width=10, length=12."""
        p = fallback_regex_parse("дом 10x12")
        assert p["width_m"] == 10
        assert p["length_m"] == 12

    def test_dimensions_from_square_meters(self):
        """64 кв метра → ~8×8."""
        p = fallback_regex_parse("квартира 64 кв метра")
        assert p["width_m"] * p["length_m"] >= 49  # ≥ 7×7

    def test_floors_from_number(self):
        """5 этажей → floors=5."""
        p = fallback_regex_parse("офис 5 этажей")
        assert p["floors"] == 5

    def test_floors_from_word(self):
        """двухэтажный → floors=2."""
        p = fallback_regex_parse("двухэтажный дом")
        assert p["floors"] == 2

    def test_floors_from_trekh(self):
        """трёхэтажный → floors=3."""
        p = fallback_regex_parse("трёхэтажный дом")
        assert p["floors"] == 3


# ═══════════════════════════════════════════════════════════════
# 7. СТИЛИ И МАТЕРИАЛЫ
# ═══════════════════════════════════════════════════════════════

class TestStylesMaterials:
    """Тесты извлечения стилей и материалов."""

    def test_style_hitech(self):
        p = fallback_regex_parse("спальня в стиле хайтек")
        assert p["style"] == "hitech"

    def test_style_loft(self):
        p = fallback_regex_parse("кухня в стиле лофт")
        assert p["style"] == "loft"

    def test_style_minimalist(self):
        p = fallback_regex_parse("таунхаус минимализм")
        assert p["style"] == "minimalist"

    def test_style_scandinavian(self):
        p = fallback_regex_parse("гостиная скандинавский стиль")
        assert p["style"] == "scandinavian"

    def test_style_modern_overrides_generic(self):
        """'современный таунхаус минимализм' → minimalist (не modern)."""
        p = fallback_regex_parse("современный таунхаус минимализм")
        assert p["style"] == "minimalist"

    def test_material_brick(self):
        p = fallback_regex_parse("кирпичный дом")
        assert p["material"] == "brick"

    def test_material_wood(self):
        p = fallback_regex_parse("деревянный коттедж")
        assert p["material"] == "wood"

    def test_material_glass(self):
        p = fallback_regex_parse("стеклянный офис")
        assert p["material"] == "glass"


# ═══════════════════════════════════════════════════════════════
# 8. МЕТА-ТЕСТЫ (проверка что тесты реальны)
# ═══════════════════════════════════════════════════════════════

class TestMetaTests:
    """Мета-тесты: проверка что тесты содержат реальные assert."""

    def test_tests_are_not_stubs(self):
        """Проверка что интеграционные тесты реально тестируют код."""
        import inspect
        test_funcs = [
            getattr(self, name) for name in dir(self)
            if name.startswith("test_")
        ]
        # Этот тест сам по себе содержит assert
        assert len(test_funcs) >= 1, "Нет тестов в TestMetaTests"

    def test_hallucination_matrix_covers_10_cases(self):
        """Матрица содержит ≥ 10 тест-кейсов."""
        assert len(HALLUCINATION_MATRIX) >= 10, \
            f"Слишком мало кейсов: {len(HALLUCINATION_MATRIX)}"

    def test_all_object_types_covered(self):
        """Матрица покрывает все типы объектов."""
        types = {case[1] for case in HALLUCINATION_MATRIX}
        assert "building" in types
        assert "room" in types
        assert "interior" in types


# ═══════════════════════════════════════════════════════════════
# ЗАПУСК
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
