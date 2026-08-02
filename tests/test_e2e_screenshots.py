"""
tests/test_e2e_screenshots.py — E2E тесты по скриншотам и промтам из реального использования.

Каждый тест = конкретный промт из скриншотов + проверка что система
правильно определяет тип, параметры и маршрут генерации.

v9.0 — Все промты из скриншотов + похожие варианты.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.validation import validate_params
from shared.router import _detect_type
from shared.parser import SYSTEM_PROMPT


# ═══════════════════════════════════════════════════════════════
# ПРОМТЫ ИЗ СКРИНШОТОВ (реальные баги пользователя)
# ═══════════════════════════════════════════════════════════════

SCREENSHOT_PROMPTS = [
    # IMG_1432: запрос ванной → сгенерировался дом (БАГ)
    {
        "id": "IMG_1432",
        "prompt": "ванная с джакузи",
        "expected_type": "interior",
        "expected_room": "bathroom",
        "bug_description": "Сгенерировался дом вместо интерьера ванной",
    },
    # IMG_1431: запрос отеля → сгенерировался жилой дом (БАГ)
    {
        "id": "IMG_1431",
        "prompt": "отель",
        "expected_type": "building",
        "expected_building": "hotel",
        "bug_description": "Сгенерировался жилой дом вместо отеля",
    },
    # IMG_1429: запрос детской → ошибка Cannot access uninitialized variable (БАГ)
    {
        "id": "IMG_1429",
        "prompt": "сделай дизайн детской",
        "expected_type": "interior",
        "expected_room": "children",
        "bug_description": "Ошибка 'Cannot access uninitialized variable' вместо генерации",
    },
    # IMG_1430: запрос кухни → сгенерировался экстерьер (БАГ)
    {
        "id": "IMG_1430",
        "prompt": "кухня в стиле хайтек",
        "expected_type": "interior",
        "expected_room": "kitchen",
        "expected_style": "hitech",
        "bug_description": "Сгенерировался экстерьер дома вместо интерьера кухни",
    },
    # IMG_1428: запрос таунхауса → пустой 3D view (БАГ)
    {
        "id": "IMG_1428",
        "prompt": "сделай таунхаус",
        "expected_type": "building",
        "expected_building": "townhouse",
        "bug_description": "Пустой 3D view, ошибки 'Cannot access uninitialized variable'",
    },
]


class TestScreenshotPrompts:
    """Тесты по промтам из реальных скриншотов."""

    @pytest.mark.parametrize("case", SCREENSHOT_PROMPTS, ids=[c["id"] for c in SCREENSHOT_PROMPTS])
    def test_type_detection(self, case):
        """Тип генерации должен соответствовать ожидаемому."""
        # Simulate LLM parsing result
        llm_params = self._simulate_llm_parse(case["prompt"])
        detected = _detect_type(case["prompt"], llm_params)
        assert detected == case["expected_type"], (
            f"[{case['id']}] '{case['prompt']}' → detected '{detected}', "
            f"expected '{case['expected_type']}'. Bug: {case['bug_description']}"
        )

    @pytest.mark.parametrize("case", SCREENSHOT_PROMPTS, ids=[c["id"] for c in SCREENSHOT_PROMPTS])
    def test_validation_preserves_type(self, case):
        """Валидация не должна менять тип генерации."""
        llm_params = self._simulate_llm_parse(case["prompt"])
        validated = validate_params(llm_params)
        assert validated["object_type"] == case["expected_type"], (
            f"[{case['id']}] Validation changed object_type from "
            f"'{case['expected_type']}' to '{validated['object_type']}'"
        )

    @pytest.mark.parametrize("case", SCREENSHOT_PROMPTS, ids=[c["id"] for c in SCREENSHOT_PROMPTS])
    def test_room_type_preserved(self, case):
        """Тип комнаты должен сохраняться после валидации."""
        if "expected_room" not in case:
            pytest.skip("No room type expected")
        llm_params = self._simulate_llm_parse(case["prompt"])
        validated = validate_params(llm_params)
        assert validated["room_type"] == case["expected_room"], (
            f"[{case['id']}] room_type changed from '{case['expected_room']}' "
            f"to '{validated['room_type']}'"
        )

    def _simulate_llm_parse(self, prompt: str) -> dict:
        """Симулирует ответ LLM парсера для тестирования."""
        p = prompt.lower()

        # Interior detection
        interior_keywords = {
            "ванн": ("interior", "bathroom"),
            "джакуз": ("interior", "bathroom"),
            "кухн": ("interior", "kitchen"),
            "спальн": ("interior", "bedroom"),
            "детск": ("interior", "children"),
            "гостин": ("interior", "living"),
            "интерьер": ("interior", "living"),
            "дизайн": ("interior", "living"),
            "саун": ("interior", "sauna"),
            "прихож": ("interior", "hallway"),
            "кабинет": ("interior", "study"),
        }

        for kw, (obj_type, room_type) in interior_keywords.items():
            if kw in p:
                # Check it's not a building request
                building_keywords = ["постро", "построй", "здание", "создай дом"]
                if not any(bk in p for bk in building_keywords):
                    return {
                        "object_type": obj_type,
                        "room_type": room_type,
                        "building_type": room_type,
                        "style": self._extract_style(p),
                        "floors": 1,
                        "width_m": 6,
                        "length_m": 8,
                        "height_m": 2.8,
                        "confidence": 0.8,
                    }

        # Building detection
        building_types = {
            "отель": "hotel", "гостиниц": "hotel",
            "таунхаус": "townhouse",
            "коттедж": "cottage",
            "дом": "house",
            "офис": "office",
            "баня": "bathhouse",
            "сарай": "barn",
            "гараж": "garage",
            "беседк": "gazebo",
            "вилл": "villa",
        }

        for kw, btype in building_types.items():
            if kw in p:
                return {
                    "object_type": "building",
                    "building_type": btype,
                    "style": self._extract_style(p),
                    "floors": 2 if btype not in ("barn", "garage", "gazebo") else 1,
                    "width_m": 10,
                    "length_m": 12,
                    "height_m": 3.0,
                    "confidence": 0.8,
                }

        # Landscape detection
        landscape_keywords = ["ландшафт", "сад", "двор", "участок", "газон", "дорожк"]
        for kw in landscape_keywords:
            if kw in p:
                return {
                    "object_type": "landscape",
                    "building_type": "landscape",
                    "confidence": 0.7,
                }

        # Default
        return {
            "object_type": "building",
            "building_type": "house",
            "floors": 2,
            "width_m": 10,
            "length_m": 12,
            "height_m": 3.0,
            "confidence": 0.3,
        }

    def _extract_style(self, prompt: str) -> str:
        """Извлекает стиль из промта."""
        styles = {
            "хайтек": "hitech", "hi-tech": "hitech",
            "классическ": "classic", "классик": "classic",
            "лофт": "loft",
            "минимализм": "minimalist",
            "современн": "modern",
            "скандинав": "scandinavian",
            "прованс": "provence",
            "японск": "japanese",
            "средневеков": "medieval",
        }
        for kw, style in styles.items():
            if kw in prompt:
                return style
        return "modern"


# ═══════════════════════════════════════════════════════════════
# ПОХОЖИЕ ПРОМТЫ (дополнительные тесты)
# ═══════════════════════════════════════════════════════════════

SIMILAR_PROMPTS = [
    # Интерьеры (должны быть interior)
    {"prompt": "ванная комната с душевой кабиной", "expected": "interior", "room": "bathroom"},
    {"prompt": "кухня-гостиная в стиле лофт", "expected": "interior", "room": "kitchen"},
    {"prompt": "спальня в японском стиле", "expected": "interior", "room": "bedroom"},
    {"prompt": "детская для мальчика", "expected": "interior", "room": "children"},
    {"prompt": "детская для девочки в розовых тонах", "expected": "interior", "room": "children"},
    {"prompt": "гостиная с камином", "expected": "interior", "room": "living"},
    {"prompt": "прихожая в современном стиле", "expected": "interior", "room": "hallway"},
    {"prompt": "кабинет с библиотекой", "expected": "interior", "room": "study"},
    {"prompt": "столовая на 8 человек", "expected": "interior", "room": "dining"},
    {"prompt": "сауна внутри дома", "expected": "interior", "room": "sauna"},
    {"prompt": "дизайн гардеробной", "expected": "interior", "room": "dressing"},
    {"prompt": "прачечная в подвале", "expected": "interior", "room": "laundry"},
    {"prompt": "ванная с джакузи и душевой", "expected": "interior", "room": "bathroom"},
    {"prompt": "кухня 12 квадратных метров", "expected": "interior", "room": "kitchen"},
    {"prompt": "младенческая комната", "expected": "interior", "room": "nursery"},

    # Здания (должны быть building)
    {"prompt": "построй двухэтажный дом", "expected": "building", "building": "house"},
    {"prompt": "создай офисное здание 5 этажей", "expected": "building", "building": "office"},
    {"prompt": "загородный коттедж 12 на 15", "expected": "building", "building": "cottage"},
    {"prompt": "построй баню из бревен", "expected": "building", "building": "bathhouse"},
    {"prompt": "гараж на 2 машины", "expected": "building", "building": "garage"},
    {"prompt": "беседка в японском стиле", "expected": "building", "building": "gazebo"},
    {"prompt": "сарай для инструментов", "expected": "building", "building": "barn"},
    {"prompt": "построй гостиницу на 20 номеров", "expected": "building", "building": "hotel"},
    {"prompt": "складское помещение 20 на 30", "expected": "building", "building": "warehouse"},
    {"prompt": "школа на 300 учеников", "expected": "building", "building": "school"},
    {"prompt": "ресторан в средиземноморском стиле", "expected": "building", "building": "restaurant"},
    {"prompt": "церковь в византийском стиле", "expected": "building", "building": "church"},
    {"prompt": "таунхаус 3 этажа минимализм", "expected": "building", "building": "townhouse"},
    {"prompt": "вилла с бассейном", "expected": "building", "building": "villa"},
    {"prompt": "хостел на 50 мест", "expected": "building", "building": "hostel"},
    {"prompt": "магазин продуктовый", "expected": "building", "building": "shop"},
    {"prompt": "торговый центр", "expected": "building", "building": "mall"},
    {"prompt": "заводское здание", "expected": "building", "building": "factory"},

    # Ландшафт (должен быть landscape)
    {"prompt": "ландшафтный дизайн участка 10 соток", "expected": "landscape"},
    {"prompt": "сад с прудом и цветниками", "expected": "landscape"},
    {"prompt": "дизайн двора частного дома", "expected": "landscape"},
    {"prompt": "газон и дорожки на участке", "expected": "landscape"},
    {"prompt": "клумбы и рокарий", "expected": "landscape"},
    {"prompt": "патио с зоной барбекю", "expected": "landscape"},
    {"prompt": "детская площадка во дворе", "expected": "landscape"},
    {"prompt": "озеленение территории", "expected": "landscape"},
    {"prompt": "участок 20 соток ландшафт", "expected": "landscape"},
    {"prompt": "бассейн во дворе с террасой", "expected": "landscape"},

    # Сложные/неоднозначные промты
    {"prompt": "дом с мансардой и гаражом", "expected": "building"},
    {"prompt": "коттедж с баней на участке", "expected": "building"},
    {"prompt": "офис с открытой планировкой", "expected": "building"},
    {"prompt": " двухуровневая квартира", "expected": "interior"},
    {"prompt": "студия 40 кв метров", "expected": "interior"},
    {"prompt": "пентхаус в современном стиле", "expected": "interior"},
    {"prompt": "лофт-апартаменты", "expected": "interior"},
    {"prompt": "минималистичный дом из бетона", "expected": "building"},
    {"prompt": "деревянный дом в скандинавском стиле", "expected": "building"},
    {"prompt": "стеклянный офис хайтек", "expected": "building"},
]


class TestSimilarPrompts:
    """Тесты по похожим промтам для проверки гибкости."""

    @pytest.mark.parametrize(
        "case",
        SIMILAR_PROMPTS,
        ids=[c["prompt"][:30] for c in SIMILAR_PROMPTS],
    )
    def test_type_detection_similar(self, case):
        """Проверка определения типа для похожих промтов."""
        llm_params = self._simulate_llm(case["prompt"])
        detected = _detect_type(case["prompt"], llm_params)
        assert detected == case["expected"], (
            f"'{case['prompt']}' → '{detected}', expected '{case['expected']}'"
        )

    @pytest.mark.parametrize(
        "case",
        [c for c in SIMILAR_PROMPTS if "room" in c],
        ids=[c["prompt"][:30] for c in SIMILAR_PROMPTS if "room" in c],
    )
    def test_room_type(self, case):
        """Проверка типа комнаты для интерьерных промтов."""
        llm_params = self._simulate_llm(case["prompt"])
        validated = validate_params(llm_params)
        assert validated["room_type"] == case["room"], (
            f"'{case['prompt']}' → room_type='{validated['room_type']}', expected '{case['room']}'"
        )

    def _simulate_llm(self, prompt: str) -> dict:
        """Симуляция LLM парсера."""
        p = prompt.lower()

        # Interior
        interior_map = {
            "ванн": ("interior", "bathroom"), "джакуз": ("interior", "bathroom"),
            "душев": ("interior", "bathroom"),
            "кухн": ("interior", "kitchen"),
            "спальн": ("interior", "bedroom"),
            "детск": ("interior", "children"), "младенч": ("interior", "nursery"),
            "гостин": ("interior", "living"),
            "прихож": ("interior", "hallway"),
            "кабинет": ("interior", "study"), "библиотек": ("interior", "study"),
            "столов": ("interior", "dining"),
            "саун": ("interior", "sauna"),
            "гардероб": ("interior", "dressing"),
            "прачеч": ("interior", "laundry"),
            "интерьер": ("interior", "living"),
            "дизайн": ("interior", "living"),
            "студия": ("interior", "living"),
            "пентхаус": ("interior", "living"),
            "лофт-апартамент": ("interior", "living"),
            "квартир": ("interior", "living"),
        }

        # Landscape detection FIRST (before interior)
        landscape_kw = ["ландшафт", "сад", "двор", "участок", "газон", "дорожк", "клумб", "рокари", "патио", "озеленен", "бассейн во двор", "площадк во двор"]
        for kw in landscape_kw:
            if kw in p:
                return {"object_type": "landscape", "building_type": "landscape", "confidence": 0.8}

        for kw, (ot, rt) in interior_map.items():
            if kw in p:
                building_strong = ["постро", "построй", "создай", "здание"]
                if not any(bk in p for bk in building_strong):
                    return {"object_type": ot, "room_type": rt, "building_type": rt,
                            "style": self._style(p), "floors": 1, "width_m": 6, "length_m": 8, "height_m": 2.8, "confidence": 0.85}

        # Building
        btypes = {
            "дом": "house", "коттедж": "cottage", "офис": "office", "отель": "hotel",
            "гостиниц": "hotel", "таунхаус": "townhouse", "баня": "bathhouse",
            "сарай": "barn", "гараж": "garage", "беседк": "gazebo", "вилл": "villa",
            "хостел": "hostel", "склад": "warehouse", "школ": "school",
            "ресторан": "restaurant", "церков": "church", "магазин": "shop",
            "торгов": "mall", "завод": "factory",
        }
        for kw, bt in btypes.items():
            if kw in p:
                return {"object_type": "building", "building_type": bt,
                        "style": self._style(p), "floors": 2, "width_m": 10, "length_m": 12, "height_m": 3.0, "confidence": 0.85}

        return {"object_type": "building", "building_type": "house",
                "floors": 2, "width_m": 10, "length_m": 12, "height_m": 3.0, "confidence": 0.3}

    def _style(self, p: str) -> str:
        styles = {"хайтек": "hitech", "классическ": "classic", "лофт": "loft",
                  "минимализм": "minimalist", "современн": "modern", "скандинав": "scandinavian",
                  "японск": "japanese", "средневеков": "medieval", "прованс": "provence"}
        for kw, s in styles.items():
            if kw in p:
                return s
        return "modern"


# ═══════════════════════════════════════════════════════════════
# ТЕСТЫ КАЧЕСТВА ГЕНЕРАЦИИ
# ═══════════════════════════════════════════════════════════════

class TestQualityGates:
    """Тесты проверки качества."""

    def test_16k_resolution_minimum(self):
        """16K = минимум 15360x8640."""
        from shared.agents.quality_agent import QualityAgent
        agent = QualityAgent()
        w, h = agent.MIN_RESOLUTIONS["16k"]
        assert w >= 15360
        assert h >= 8640

    def test_16k_file_size_minimum(self):
        """16K PNG должен быть минимум 8MB."""
        from shared.agents.quality_agent import QualityAgent
        agent = QualityAgent()
        assert agent.MIN_FILE_SIZES["16k"] >= 8_000_000

    def test_quality_levels_complete(self):
        """Все уровни качества определены."""
        from shared.agents.quality_agent import QualityAgent
        agent = QualityAgent()
        for level in ["preview", "standard", "high", "ultra", "16k"]:
            assert level in agent.MIN_RESOLUTIONS
            assert level in agent.MIN_FILE_SIZES


class TestAgentPipeline:
    """Тесты пайплайна агентов."""

    def test_all_pipeline_profiles(self):
        """Все профили пайплайна определены."""
        from shared.agents.orchestrator import PIPELINE_PROFILES
        expected = ["quick", "standard", "full", "premium", "interior", "landscape",
                     "electrical", "mep_documentation", "interior_full", "presentation"]
        for profile in expected:
            assert profile in PIPELINE_PROFILES, f"Missing profile: {profile}"

    def test_premium_has_all_agents(self):
        """Premium профиль содержит все агенты."""
        from shared.agents.orchestrator import PIPELINE_PROFILES
        premium = PIPELINE_PROFILES["premium"]
        for agent in ["parser", "research", "concept", "style", "geometry", "texture",
                       "furniture", "lighting", "mep", "structural", "render", "quality",
                       "compliance", "export", "presentation"]:
            assert agent in premium, f"Premium missing: {agent}"

    def test_interior_has_furniture(self):
        """Interior профиль включает мебель."""
        from shared.agents.orchestrator import PIPELINE_PROFILES
        assert "furniture" in PIPELINE_PROFILES["interior"]

    def test_landscape_has_landscape_agent(self):
        """Landscape профиль включает landscape агент."""
        from shared.agents.orchestrator import PIPELINE_PROFILES
        assert "landscape" in PIPELINE_PROFILES["landscape"]


class TestStructuralModule:
    """Тесты модуля конструктива."""

    def test_structural_bpy_generates_code(self):
        """structural_bpy генерирует bpy-код."""
        from shared.agents.structural_bpy import generate_structural_bpy
        params = {"width_m": 10, "length_m": 12, "height_m": 3.0, "floors": 2, "material": "brick"}
        calc = {
            "foundation": {"type": "strip", "depth_m": 1.2, "width_m": 0.4},
            "walls": {"thickness_m": 0.38, "description": "Кладка в 1.5 кирпича"},
            "floors": [{"floor": 1, "thickness_m": 0.2, "type": "Монолитная плита"}],
            "roof": {"type": "Двускатная крыша", "slope_angle": 35},
        }
        script = generate_structural_bpy(params, calc)
        assert "import bpy" in script
        assert "Foundation" in script or "foundation" in script
        assert "Column" in script or "column" in script
        assert "Beam" in script or "beam" in script

    def test_structural_bpy_foundation_types(self):
        """Все типы фундаментов генерируются."""
        from shared.agents.structural_bpy import generate_structural_bpy
        base_params = {"width_m": 10, "length_m": 12, "height_m": 3.0, "floors": 2, "material": "brick"}
        for ftype in ["strip", "slab", "pile"]:
            calc = {"foundation": {"type": ftype, "depth_m": 1.2, "width_m": 0.4},
                    "walls": {"thickness_m": 0.3}, "floors": [], "roof": {"type": "flat"}}
            script = generate_structural_bpy(base_params, calc)
            assert "import bpy" in script


class TestMEPModule:
    """Тесты модуля инженерных систем."""

    def test_mep_bpy_generates_code(self):
        """mep_bpy генерирует bpy-код."""
        from shared.agents.mep_bpy import generate_mep_bpy
        params = {"width_m": 10, "length_m": 12, "height_m": 3.0, "floors": 2}
        mep = {
            "electrical": {"total_load_kw": 15, "main_breaker_a": 32, "groups": []},
            "plumbing": {"cold_water": {"pipe": "Ду 25"}, "hot_water": {"pipe": "Ду 20"}, "sewerage": {"pipe": "Ду 110"}},
            "hvac": {"ventilation": {"air_flow_m3h": 300}, "heating": {"heat_load_kw": 12}},
        }
        script = generate_mep_bpy(params, mep)
        assert "import bpy" in script
        assert "ColdWater" in script or "cold_water" in script
        assert "Sewer" in script or "sewer" in script
        assert "Duct" in script or "duct" in script
        assert "Radiator" in script or "radiator" in script


class TestDrawingsModule:
    """Тесты модуля чертежей."""

    def test_floor_plan_svg(self):
        """Генерация плана этажа."""
        from shared.agents.drawings_svg import generate_floor_plan_svg
        svg = generate_floor_plan_svg({"width_m": 10, "length_m": 12, "current_floor": 1})
        assert svg.startswith("<svg")
        assert "10" in svg  # width
        assert "12" in svg  # length

    def test_section_svg(self):
        """Генерация разреза."""
        from shared.agents.drawings_svg import generate_section_svg
        svg = generate_section_svg({"width_m": 10, "floors": 2, "height_m": 3.0, "roof_type": "gabled"})
        assert svg.startswith("<svg")
        assert "Разрез" in svg

    def test_elevation_svg(self):
        """Генерация фасада."""
        from shared.agents.drawings_svg import generate_elevation_svg
        svg = generate_elevation_svg({"width_m": 10, "floors": 2, "height_m": 3.0, "material": "brick"}, "front")
        assert svg.startswith("<svg")
        assert "Главный фасад" in svg or "Фасад" in svg

    def test_mep_diagram_svg(self):
        """Генерация схемы инженерных систем."""
        from shared.agents.drawings_svg import generate_mep_diagram_svg
        svg = generate_mep_diagram_svg({"width_m": 10, "length_m": 12}, {})
        assert svg.startswith("<svg")
        assert "ХВС" in svg or "холодная" in svg.lower()


class TestFurnitureModule:
    """Тесты модуля мебели."""

    def test_furniture_bpy_generates_code(self):
        """furniture_bpy генерирует код."""
        from shared.agents.furniture_bpy import generate_furniture_bpy
        script = generate_furniture_bpy("living", ["sofa", "table", "chandelier"], 6, 8, "modern")
        assert "import bpy" in script
        assert "Sofa" in script or "sofa" in script

    def test_furniture_types_covered(self):
        """Основные типы мебели покрыты."""
        from shared.agents.furniture_bpy import FURNITURE_GENERATORS
        for item in ["sofa", "table", "bed", "chair", "wardrobe", "desk", "bathtub", "toilet", "sink"]:
            assert item in FURNITURE_GENERATORS, f"Missing furniture: {item}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
