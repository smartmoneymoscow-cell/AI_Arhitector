"""
test_orchestrator.py — Тесты multi-agent оркестратора и router.

Покрывает:
  - shared/router.py — маршрутизация, шаблоны, building params
  - shared/agents/ — orchestrator, parser, geometry, texture, render, export

Запуск:
  python3 -m pytest tests/test_orchestrator.py -v
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.router import route_generation, GenerationPlan, BUILDING_TEMPLATES
from shared.agents import (
    Orchestrator, ParserAgent, GeometryAgent,
    TextureAgent, RenderAgent, ExportAgent,
)
from shared.agents.base import Task, TaskResult, TaskStatus


# ═══════════════════════════════════════════════════════════════
#1. ROUTER TESTS
# ═══════════════════════════════════════════════════════════════

class TestRouter:
    """Тесты маршрутизации генерации."""

    def test_basic_building_route(self):
        plan = route_generation("двухэтажный кирпичный дом 10×12")
        assert plan.gen_type == "building"
        assert plan.params["building"]["W"] == 10.0
        assert plan.params["building"]["L"] == 12.0
        assert plan.params["building"]["floors"] == 2
        assert plan.params["building"]["mat"] == "brick"

    def test_interior_route(self):
        plan = route_generation("спальня в стиле хайтек")
        assert plan.gen_type == "interior"

    def test_office_route(self):
        plan = route_generation("офис 5 этажей стекло 20×24")
        assert plan.gen_type == "building"
        assert plan.params["building"]["floors"] == 5
        assert plan.params["building"]["W"] == 20.0
        assert plan.params["building"]["L"] == 24.0
        assert plan.params["building"]["mat"] == "glass"

    def test_cottage_template(self):
        plan = route_generation("коттедж 12×15 дерево")
        assert plan.params["building"]["mat"] == "wood"
        assert plan.params["building"]["W"] == 12.0
        assert plan.params["building"]["L"] == 15.0

    def test_balcony_feature(self):
        plan = route_generation("дом2 этажа с балконом")
        assert plan.params["building"].get("balcony") is True

    def test_garage_feature(self):
        plan = route_generation("дом с гаражом")
        assert plan.params["building"].get("has_garage") is True

    def test_terrace_feature(self):
        plan = route_generation("коттедж с террасой")
        assert plan.params["building"].get("has_terrace") is True

    def test_style_hitech(self):
        plan = route_generation("здание в стиле хайтек")
        assert plan.params["parsed"]["style"] == "hitech"

    def test_style_loft(self):
        plan = route_generation("кухня в стиле лофт")
        assert plan.gen_type == "interior"
        assert plan.params["parsed"]["style"] == "loft"

    def test_plan_has_steps(self):
        plan = route_generation("дом 2 этажа")
        assert len(plan.steps) >= 3  # parse + geometry + export

    def test_plan_job_id(self):
        plan = route_generation("дом")
        assert plan.job_id is not None
        assert len(plan.job_id) == 8

    def test_default_template_fallback(self):
        """Неизвестный тип → house template."""
        plan = route_generation("построй что-нибудь")
        assert plan.params["building"]["label"] in (
            "Жилой дом", "Офисный центр", "Загородный коттедж", "Таунхаус"
        )

    def test_building_templates_complete(self):
        """Все шаблоны содержат обязательные поля."""
        required = {"label", "floors", "W", "L", "fH", "roof", "mat", "rooms"}
        for name, tpl in BUILDING_TEMPLATES.items():
            for key in required:
                assert key in tpl, f"Template '{name}' missing '{key}'"

    def test_material_colors(self):
        """Материалы корректно подставляют цвета."""
        plan = route_generation("деревянный дом")
        assert plan.params["building"]["fc"] == "#b8864e"
        assert plan.params["building"]["rc"] == "#3e2005"


# ═══════════════════════════════════════════════════════════════
#2. AGENT TESTS
# ═══════════════════════════════════════════════════════════════

class TestParserAgent:
    def test_parse_building(self):
        agent = ParserAgent()
        task = Task(name="parse", agent="parser", params={"prompt": "кирпичный дом2 этажа"})
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert result.data["gen_type"] == "building"
        assert result.data["params"]["material"] == "brick"

    def test_parse_interior(self):
        agent = ParserAgent()
        task = Task(name="parse", agent="parser", params={"prompt": "спальня в стиле лофт"})
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert result.data["gen_type"] == "interior"

    def test_confidence_score(self):
        agent = ParserAgent()
        task = Task(name="parse", agent="parser", params={"prompt": "дом"})
        result = agent.process(task)
        assert 0.0 <= result.data["confidence"] <= 1.0


class TestGeometryAgent:
    def test_generate_building_script(self):
        agent = GeometryAgent()
        task = Task(name="geom", agent="geometry", params={
            "gen_type": "building",
            "building_params": {"width": 10, "length": 12, "floors": 2, "roof_type": "gabled",
                                "facade_material": "brick"},
        })
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert "import bpy" in result.data["script"]

    def test_generate_interior_script(self):
        agent = GeometryAgent()
        task = Task(name="geom", agent="geometry", params={
            "gen_type": "interior",
            "interior_params": {"width": 6, "length": 8, "height": 3, "style": "modern",
                                "furniture": ["sofa", "table"]},
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
        assert len(subtasks) >= 5  # 3 floors + roof + balcony + landscape


class TestTextureAgent:
    def test_brick_texture(self):
        agent = TextureAgent()
        task = Task(name="tex", agent="texture", params={"material": "brick", "resolution": 2048})
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert result.data["material"] == "brick"
        assert result.data["roughness"] == 0.88

    def test_glass_texture(self):
        agent = TextureAgent()
        task = Task(name="tex", agent="texture", params={"material": "glass"})
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert result.data["transparent"] is True


class TestRenderAgent:
    def test_preview_preset(self):
        agent = RenderAgent()
        task = Task(name="render", agent="render", params={"quality": "preview"})
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert result.data["preset"]["resolution_x"] == 1280

    def test_ultra_preset(self):
        agent = RenderAgent()
        task = Task(name="render", agent="render", params={"quality": "ultra"})
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert result.data["preset"]["engine"] == "CYCLES"
        assert result.data["preset"]["resolution_x"] == 3840


class TestExportAgent:
    def test_glb_export(self):
        agent = ExportAgent()
        task = Task(name="export", agent="export", params={"format": "glb", "job_id": "test123"})
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert "export_scene.gltf" in result.data["export_command"]

    def test_unsupported_format(self):
        agent = ExportAgent()
        task = Task(name="export", agent="export", params={"format": "xyz"})
        result = agent.process(task)
        assert result.status == TaskStatus.FAILED


# ═══════════════════════════════════════════════════════════════
#3. ORCHESTRATOR TESTS
# ═══════════════════════════════════════════════════════════════

class TestOrchestrator:
    def test_full_building_execution(self):
        orch = Orchestrator()
        result = orch.execute("двухэтажный кирпичный дом 10×12")
        assert result["status"] == "done"
        assert result["result"]["gen_type"] == "building"
        assert len(result["steps"]) >= 3

    def test_full_interior_execution(self):
        orch = Orchestrator()
        result = orch.execute("спальня в стиле минимализм")
        assert result["status"] == "done"
        assert result["result"]["gen_type"] == "interior"

    def test_job_id_unique(self):
        orch = Orchestrator()
        r1 = orch.execute("дом")
        r2 = orch.execute("дом")
        assert r1["job_id"] != r2["job_id"]

    def test_progress_tracking(self):
        orch = Orchestrator()
        result = orch.execute("дом2 этажа")
        progress = orch.get_progress(result["job_id"])
        assert progress["status"] == "done"
        assert progress["progress"] == 100

    def test_job_not_found(self):
        orch = Orchestrator()
        progress = orch.get_progress("nonexistent")
        assert "error" in progress

    def test_steps_timing(self):
        orch = Orchestrator()
        result = orch.execute("офис5 этажей стекло")
        for step in result["steps"]:
            assert "name" in step
            assert "status" in step

    def test_error_handling(self):
        """Orchestrator не падает на нестандартных промтах."""
        orch = Orchestrator()
        result = orch.execute("🤖💀")
        assert result["status"] == "done"  # regex fallback handles it

    def test_params_passed_to_geometry(self):
        orch = Orchestrator()
        result = orch.execute("деревянный коттедж 12×15")
        geom_step = next(s for s in result["steps"] if s["name"] == "geometry")
        assert geom_step["status"] == "done"

    def test_material_in_result(self):
        orch = Orchestrator()
        result = orch.execute("кирпичный дом")
        assert result["result"]["params"]["material"] == "brick"

    def test_dimensions_in_result(self):
        orch = Orchestrator()
        result = orch.execute("дом20×30")
        building = result["result"]["building_params"]
        assert building["W"] == 20.0
        assert building["L"] == 30.0


# ═══════════════════════════════════════════════════════════════
#4. EDGE CASES
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_empty_prompt(self):
        orch = Orchestrator()
        result = orch.execute("")
        assert result["status"] == "done"

    def test_very_long_prompt(self):
        orch = Orchestrator()
        result = orch.execute("дом " * 1000)
        assert result["status"] == "done"

    def test_special_characters(self):
        orch = Orchestrator()
        result = orch.execute("<script>alert(1)</script>")
        assert result["status"] == "done"

    def test_mixed_language(self):
        plan = route_generation("modern house 2 floors brick 10x12")
        assert plan.gen_type == "building"

    def test_numbers_only(self):
        plan = route_generation("10×12×3")
        assert plan.gen_type == "building"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
