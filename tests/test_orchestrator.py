"""
test_orchestrator.py — Тесты multi-agent оркестратора и router.

v6.0 — LLM-only парсинг. Все вызовы парсера замоканы.

Запуск:
  python3 -m pytest tests/test_orchestrator.py -v
"""

import sys
import os
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.router import route_generation, GenerationPlan, BUILDING_TEMPLATES
from shared.agents import (
    Orchestrator, ParserAgent, GeometryAgent,
    TextureAgent, RenderAgent, ExportAgent,
)
from shared.agents.base import Task, TaskResult, TaskStatus


# ═══════════════════════════════════════════════════════════════
# MOCK LLM
# ═══════════════════════════════════════════════════════════════

MOCK_RESPONSES = {
    "двухэтажный кирпичный дом 10×12": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "brick", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.95},
    "спальня в стиле хайтек": {"object_type": "room", "room_type": "bedroom", "floors": 1, "width_m": 5, "length_m": 6, "style": "hitech", "material": "plaster", "roof_type": "flat", "features": [], "furniture": ["bed", "wardrobe", "nightstand"], "confidence": 0.85},
    "офис 5 этажей стекло 20×24": {"object_type": "building", "building_type": "office", "floors": 5, "width_m": 20, "length_m": 24, "style": "modern", "material": "glass", "roof_type": "flat", "features": [], "furniture": [], "confidence": 0.95},
    "коттедж 12×15 дерево": {"object_type": "building", "building_type": "cottage", "floors": 2, "width_m": 12, "length_m": 15, "style": "modern", "material": "wood", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.9},
    "дом с балконом": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster", "roof_type": "gabled", "features": ["balcony"], "furniture": [], "confidence": 0.8},
    "дом с гаражом": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster", "roof_type": "gabled", "features": ["garage"], "furniture": [], "confidence": 0.8},
    "коттедж с террасой": {"object_type": "building", "building_type": "cottage", "floors": 2, "width_m": 12, "length_m": 15, "style": "modern", "material": "plaster", "roof_type": "gabled", "features": ["terrace"], "furniture": [], "confidence": 0.8},
    "здание в стиле хайтек": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "hitech", "material": "glass", "roof_type": "flat", "features": [], "furniture": [], "confidence": 0.8},
    "кухня в стиле лофт": {"object_type": "room", "room_type": "kitchen", "floors": 1, "width_m": 4, "length_m": 5, "style": "loft", "material": "plaster", "roof_type": "flat", "features": [], "furniture": ["table", "sink", "stove"], "confidence": 0.9},
    "дом 2 этажа": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.7},
    "построй что-нибудь": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.3},
    "деревянный дом": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "wood", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.7},
    "кирпичный дом": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "brick", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.7},
    "спальня в стиле минимализм": {"object_type": "room", "room_type": "bedroom", "floors": 1, "width_m": 5, "length_m": 6, "style": "minimalist", "material": "plaster", "roof_type": "flat", "features": [], "furniture": ["bed", "wardrobe", "nightstand"], "confidence": 0.85},
    "офис 5 этажей стекло": {"object_type": "building", "building_type": "office", "floors": 5, "width_m": 20, "length_m": 24, "style": "modern", "material": "glass", "roof_type": "flat", "features": [], "furniture": [], "confidence": 0.9},
    "дом 20×30": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 20, "length_m": 30, "style": "modern", "material": "plaster", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.9},
    "деревянный коттедж 12×15": {"object_type": "building", "building_type": "cottage", "floors": 2, "width_m": 12, "length_m": 15, "style": "modern", "material": "wood", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.9},
    "modern house 2 floors brick 10x12": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "brick", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.9},
    "10×12×3": {"object_type": "building", "building_type": "house", "floors": 2, "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster", "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.5},
}


def _mock_call_llm(text, cfg):
    for key, resp in MOCK_RESPONSES.items():
        if key in text or text in key:
            return resp
    return {"object_type": "building", "building_type": "house", "floors": 2,
            "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster",
            "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.5}


# ═══════════════════════════════════════════════════════════════
# 1. ROUTER TESTS
# ═══════════════════════════════════════════════════════════════

class TestRouter:
    """Тесты маршрутизации генерации."""

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_basic_building_route(self, mock):
        plan = route_generation("двухэтажный кирпичный дом 10×12")
        assert plan.gen_type == "building"
        assert plan.params["building"]["W"] == 10.0
        assert plan.params["building"]["L"] == 12.0
        assert plan.params["building"]["floors"] == 2
        assert plan.params["building"]["mat"] == "brick"

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_interior_route(self, mock):
        plan = route_generation("спальня в стиле хайтек")
        assert plan.gen_type == "interior"

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_office_route(self, mock):
        plan = route_generation("офис 5 этажей стекло 20×24")
        assert plan.gen_type == "building"
        assert plan.params["building"]["floors"] == 5
        assert plan.params["building"]["W"] == 20.0
        assert plan.params["building"]["L"] == 24.0
        assert plan.params["building"]["mat"] == "glass"

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_cottage_template(self, mock):
        plan = route_generation("коттедж 12×15 дерево")
        assert plan.params["building"]["mat"] == "wood"
        assert plan.params["building"]["W"] == 12.0
        assert plan.params["building"]["L"] == 15.0

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_balcony_feature(self, mock):
        plan = route_generation("дом с балконом")
        assert plan.params["building"].get("balcony") is True

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_garage_feature(self, mock):
        plan = route_generation("дом с гаражом")
        assert plan.params["building"].get("has_garage") is True

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_terrace_feature(self, mock):
        plan = route_generation("коттедж с террасой")
        assert plan.params["building"].get("has_terrace") is True

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_style_hitech(self, mock):
        plan = route_generation("здание в стиле хайтек")
        assert plan.params["parsed"]["style"] == "hitech"

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_style_loft(self, mock):
        plan = route_generation("кухня в стиле лофт")
        assert plan.gen_type == "interior"
        assert plan.params["parsed"]["style"] == "loft"

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_plan_has_steps(self, mock):
        plan = route_generation("дом 2 этажа")
        assert len(plan.steps) >= 3

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_plan_job_id(self, mock):
        plan = route_generation("дом")
        assert plan.job_id is not None
        assert len(plan.job_id) == 8

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_default_template_fallback(self, mock):
        plan = route_generation("построй что-нибудь")
        assert plan.params["building"]["label"] in (
            "Жилой дом", "Офисный центр", "Загородный коттедж", "Таунхаус"
        )

    def test_building_templates_complete(self):
        required = {"label", "floors", "W", "L", "fH", "roof", "mat", "rooms"}
        for name, tpl in BUILDING_TEMPLATES.items():
            for key in required:
                assert key in tpl, f"Template '{name}' missing '{key}'"

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_material_colors(self, mock):
        plan = route_generation("деревянный дом")
        assert plan.params["building"]["fc"] == "#b8864e"
        assert plan.params["building"]["rc"] == "#3e2005"


# ═══════════════════════════════════════════════════════════════
# 2. AGENT TESTS
# ═══════════════════════════════════════════════════════════════

TEST_OUTPUT = "/tmp/arch_test_output"


class TestParserAgent:
    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_parse_building(self, mock):
        agent = ParserAgent()
        task = Task(name="parse", agent="parser", params={"prompt": "кирпичный дом"})
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert result.data["gen_type"] == "building"
        assert result.data["params"]["material"] == "brick"

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_parse_interior(self, mock):
        agent = ParserAgent()
        task = Task(name="parse", agent="parser", params={"prompt": "кухня в стиле лофт"})
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert result.data["gen_type"] == "interior"

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_confidence_score(self, mock):
        agent = ParserAgent()
        task = Task(name="parse", agent="parser", params={"prompt": "дом"})
        result = agent.process(task)
        assert 0.0 <= result.data["confidence"] <= 1.0


class TestGeometryAgent:
    def test_generate_building_script(self):
        agent = GeometryAgent()
        task = Task(name="geom", agent="geometry", params={
            "gen_type": "building",
            "building_params": {"width": 10, "length": 12, "floors": 2, "roof_type": "gabled", "facade_material": "brick"},
        })
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert "import bpy" in result.data["script"]

    def test_generate_interior_script(self):
        agent = GeometryAgent()
        task = Task(name="geom", agent="geometry", params={
            "gen_type": "interior",
            "interior_params": {"width": 6, "length": 8, "height": 3, "style": "modern", "furniture": ["sofa", "table"]},
        })
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert "import bpy" in result.data["script"]

    def test_decompose_building(self):
        agent = GeometryAgent()
        task = Task(name="geom", agent="geometry", params={
            "gen_type": "building",
            "building_params": {"floors": 3, "balcony": True},
        })
        subtasks = agent.decompose(task)
        assert len(subtasks) >= 5


class TestTextureAgent:
    def test_brick_texture(self):
        agent = TextureAgent()
        task = Task(name="tex", agent="texture", params={"material": "brick", "resolution": 2048})
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert result.data["material"] == "brick"
        assert "script" in result.data

    def test_glass_texture(self):
        agent = TextureAgent()
        task = Task(name="tex", agent="texture", params={"material": "glass"})
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert result.data["material"] == "glass"


class TestRenderAgent:
    def test_preview_preset_exists(self):
        from shared.agents.render_agent import QUALITY_PRESETS
        assert "preview" in QUALITY_PRESETS
        assert QUALITY_PRESETS["preview"]["resolution_x"] == 1280
        assert QUALITY_PRESETS["preview"]["engine"] == "BLENDER_EEVEE_NEXT"

    def test_ultra_preset_exists(self):
        from shared.agents.render_agent import QUALITY_PRESETS
        assert "ultra" in QUALITY_PRESETS
        assert QUALITY_PRESETS["ultra"]["engine"] == "CYCLES"
        assert QUALITY_PRESETS["ultra"]["resolution_x"] == 15360

    def test_16k_preset_exists(self):
        from shared.agents.render_agent import QUALITY_PRESETS
        assert "16k" in QUALITY_PRESETS
        assert QUALITY_PRESETS["16k"]["samples"] == 2048
        assert QUALITY_PRESETS["16k"]["resolution_x"] == 15360
        assert QUALITY_PRESETS["16k"]["resolution_y"] == 8640


class TestExportAgent:
    def test_glb_export_command(self):
        from shared.agents.export_agent import EXPORT_COMMANDS
        assert "glb" in EXPORT_COMMANDS
        cmd = EXPORT_COMMANDS["glb"]("/tmp/test.glb")
        assert "export_scene.gltf" in cmd

    def test_obj_export_command(self):
        from shared.agents.export_agent import EXPORT_COMMANDS
        assert "obj" in EXPORT_COMMANDS

    def test_unsupported_format(self):
        agent = ExportAgent()
        task = Task(name="export", agent="export", params={"format": "xyz"})
        result = agent.process(task)
        assert result.status == TaskStatus.FAILED


# ═══════════════════════════════════════════════════════════════
# 3. ORCHESTRATOR TESTS
# ═══════════════════════════════════════════════════════════════

class TestOrchestrator:
    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_full_building_execution(self, mock):
        orch = Orchestrator(output_dir=TEST_OUTPUT)
        result = orch.execute("двухэтажный кирпичный дом 10×12")
        assert result["status"] == "done"
        assert result["result"]["gen_type"] == "building"
        assert len(result["steps"]) >= 3

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_full_interior_execution(self, mock):
        orch = Orchestrator(output_dir=TEST_OUTPUT)
        result = orch.execute("спальня в стиле минимализм", skip_clarification=True)
        assert result["status"] == "done"
        assert result["result"]["gen_type"] == "interior"

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_job_id_unique(self, mock):
        orch = Orchestrator(output_dir=TEST_OUTPUT)
        r1 = orch.execute("дом")
        r2 = orch.execute("дом")
        assert r1["job_id"] != r2["job_id"]

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_progress_tracking(self, mock):
        orch = Orchestrator(output_dir=TEST_OUTPUT)
        result = orch.execute("дом 2 этажа", skip_clarification=True)
        progress = orch.get_progress(result["job_id"])
        assert progress["status"] == "done"
        assert progress["progress"] > 0  # some steps completed

    def test_job_not_found(self):
        orch = Orchestrator(output_dir=TEST_OUTPUT)
        progress = orch.get_progress("nonexistent")
        assert "error" in progress

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_steps_timing(self, mock):
        orch = Orchestrator(output_dir=TEST_OUTPUT)
        result = orch.execute("офис 5 этажей стекло")
        for step in result["steps"]:
            assert "name" in step
            assert "status" in step

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_params_passed_to_geometry(self, mock):
        orch = Orchestrator(output_dir=TEST_OUTPUT)
        result = orch.execute("деревянный коттедж 12×15")
        geom_step = next(s for s in result["steps"] if s["name"] == "geometry")
        assert geom_step["status"] == "done"

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_material_in_result(self, mock):
        orch = Orchestrator(output_dir=TEST_OUTPUT)
        result = orch.execute("кирпичный дом")
        assert result["result"]["params"]["material"] == "brick"

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_dimensions_in_result(self, mock):
        orch = Orchestrator(output_dir=TEST_OUTPUT)
        result = orch.execute("дом 20×30")
        building = result["result"]["building_params"]
        assert building["W"] == 20.0
        assert building["L"] == 30.0


# ═══════════════════════════════════════════════════════════════
# 4. EDGE CASES
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_empty_prompt(self):
        orch = Orchestrator(output_dir=TEST_OUTPUT)
        result = orch.execute("")
        assert result["status"] in ("done", "clarification_needed")

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_very_long_prompt(self, mock):
        orch = Orchestrator(output_dir=TEST_OUTPUT)
        result = orch.execute("дом " * 1000)
        assert result["status"] in ("done", "clarification_needed")

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_skip_clarification(self, mock):
        orch = Orchestrator(output_dir=TEST_OUTPUT)
        result = orch.execute("построй дом", skip_clarification=True)
        assert result["status"] == "done"

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_mixed_language(self, mock):
        plan = route_generation("modern house 2 floors brick 10x12")
        assert plan.gen_type == "building"

    @patch("shared.parser._call_llm", side_effect=_mock_call_llm)
    def test_numbers_only(self, mock):
        plan = route_generation("10×12×3")
        assert plan.gen_type == "building"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
