"""
shared/agents/landscape_agent.py — Агент ландшафтного дизайна.

Отвечает за:
    - Генерацию ландшафта вокруг здания
    - Размещение деревьев, кустов, газона
    - Планировку дорожек и площадок
    - Водные объекты (бассейн, пруд)
    - Озеленение фасада
"""

import logging
import random
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class LandscapeAgent(BaseAgent):
    name = "landscape"

    # База растений
    PLANTS = {
        "trees": {
            "deciduous": [
                {"name": "Дуб", "height": 15, "spread": 8, "growth": "slow"},
                {"name": "Берёза", "height": 20, "spread": 6, "growth": "fast"},
                {"name": "Клён", "height": 12, "spread": 7, "growth": "medium"},
                {"name": "Липа", "height": 15, "spread": 6, "growth": "medium"},
                {"name": "Ясень", "height": 18, "spread": 7, "growth": "fast"},
            ],
            "coniferous": [
                {"name": "Ель", "height": 20, "spread": 4, "growth": "slow"},
                {"name": "Сосна", "height": 25, "spread": 5, "growth": "medium"},
                {"name": "Лиственница", "height": 20, "spread": 5, "growth": "medium"},
                {"name": "Туя", "height": 8, "spread": 2, "growth": "slow"},
            ],
            "fruit": [
                {"name": "Яблоня", "height": 6, "spread": 5, "growth": "medium"},
                {"name": "Вишня", "height": 5, "spread": 4, "growth": "fast"},
                {"name": "Слива", "height": 5, "spread": 4, "growth": "medium"},
            ],
        },
        "shrubs": [
            {"name": "Сирень", "height": 3, "spread": 2, "bloom": "май"},
            {"name": "Гортензия", "height": 1.5, "spread": 1.5, "bloom": "июнь-август"},
            {"name": "Спирея", "height": 1, "spread": 1, "bloom": "июнь"},
            {"name": "Барбарис", "height": 1.5, "spread": 1, "bloom": "май"},
            {"name": "Чубушник", "height": 2, "spread": 1.5, "bloom": "июнь"},
        ],
        "groundcover": [
            {"name": "Газон (мятлик)", "height": 0.05, "coverage": 1.0},
            {"name": "Клевер", "height": 0.1, "coverage": 0.8},
            {"name": "Почвопокровные розы", "height": 0.3, "coverage": 0.6},
        ],
    }

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            landscape = self._generate_landscape(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=landscape,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"LandscapeAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _generate_landscape(self, params: dict) -> dict:
        """Генерация ландшафтного дизайна."""
        lot_width = params.get("lot_width_m", 30)
        lot_length = params.get("lot_length_m", 40)
        style = params.get("landscape_style", "natural")
        has_pool = params.get("has_pool", False)
        params.get("has_garden", True)
        params.get("climate", "moscow")

        # Зоны ландшафта
        zones = self._design_zones(lot_width, lot_length, params)

        # Деревья
        trees = self._place_trees(lot_width, lot_length, zones, style, params)

        # Кустарники
        shrubs = self._place_shrubs(lot_width, lot_length, zones, style)

        # Газон и покрытия
        groundcover = self._design_groundcover(lot_width, lot_length, zones, params)

        # Дорожки
        pathways = self._design_pathways(lot_width, lot_length, zones, style)

        # Водные объекты
        water_features = []
        if has_pool:
            water_features.append(self._design_pool(lot_width, lot_length, zones))

        # Освещение
        lighting = self._design_lighting(lot_width, lot_length, zones, style)

        # bpy-скрипт для Blender
        bpy_script = self._generate_bpy_script(trees, shrubs, pathways, water_features, params)

        return {
            "type": "landscape",
            "style": style,
            "zones": zones,
            "trees": trees,
            "shrubs": shrubs,
            "groundcover": groundcover,
            "pathways": pathways,
            "water_features": water_features,
            "lighting": lighting,
            "plant_count": {
                "trees": len(trees),
                "shrubs": len(shrubs),
                "groundcover_m2": sum(g.get("area_m2", 0) for g in groundcover),
            },
            "bpy_script": bpy_script,
            "maintenance": self._generate_maintenance_plan(trees, shrubs, groundcover),
        }

    def _design_zones(self, lot_w, lot_l, params) -> list[dict]:
        """Зонирование ландшафта."""
        zones = []
        params.get("landscape_style", "natural")

        # Парадная зона (перед домом)
        zones.append(
            {
                "name": "front_garden",
                "label": "Парадная зона",
                "description": "Декоративные клумбы, мощение, освещение",
                "priority": "high",
                "features": ["цветники", "мощение", "фонари"],
            }
        )

        # Зона отдыха (за домом)
        zones.append(
            {
                "name": "recreation",
                "label": "Зона отдыха",
                "description": "Терраса, мангал, места для сидения",
                "priority": "high",
                "features": ["терраса", "пергола", "мангал"],
            }
        )

        # Сад
        if params.get("has_garden", True):
            zones.append(
                {
                    "name": "garden",
                    "label": "Сад",
                    "description": "Плодовые деревья, ягодные кустарники",
                    "priority": "medium",
                    "features": ["фруктовые деревья", "грядки", "теплица"],
                }
            )

        # Детская площадка
        if params.get("has_playground", False):
            zones.append(
                {
                    "name": "playground",
                    "label": "Детская площадка",
                    "description": "Песочница, качели, горка",
                    "priority": "medium",
                    "features": ["песочница", "качели", "горка", "мягкое покрытие"],
                }
            )

        return zones

    def _place_trees(self, lot_w, lot_l, zones, style, params=None) -> list[dict]:
        """Размещение деревьев."""
        trees = []
        tree_type = "deciduous" if style in ("natural", "природный", "english") else "coniferous"

        # Деревья по периметру
        spacing = 5.0
        for x in range(2, int(lot_w) - 2, int(spacing)):
            species = random.choice(self.PLANTS["trees"][tree_type])
            trees.append(
                {
                    "name": species["name"],
                    "x": x,
                    "y": 2,
                    "height": species["height"],
                    "spread": species["spread"],
                    "type": "perimeter",
                }
            )

        # Фруктовые деревья в саду
        if (params or {}).get("has_garden", True):
            for x in range(3, min(15, int(lot_w)), 5):
                for y in range(3, min(10, int(lot_l)), 5):
                    species = random.choice(self.PLANTS["trees"]["fruit"])
                    trees.append(
                        {
                            "name": species["name"],
                            "x": x,
                            "y": y,
                            "height": species["height"],
                            "spread": species["spread"],
                            "type": "fruit",
                        }
                    )

        return trees

    def _place_shrubs(self, lot_w, lot_l, zones, style) -> list[dict]:
        """Размещение кустарников."""
        shrubs = []
        # Кустарники вдоль дорожек и забора
        for i, species in enumerate(self.PLANTS["shrubs"]):
            shrubs.append(
                {
                    "name": species["name"],
                    "x": 2 + i * 3,
                    "y": lot_l - 3,
                    "height": species["height"],
                    "spread": species["spread"],
                    "bloom": species["bloom"],
                }
            )
        return shrubs

    def _design_groundcover(self, lot_w, lot_l, zones, params=None) -> list[dict]:
        """Покрытия (газон, клевер)."""
        total_area = lot_w * lot_l
        building_area = (
            (params or {}).get("width_m", 10) * (params or {}).get("length_m", 12) if isinstance(params, dict) else 120
        )
        lawn_area = total_area - building_area - 50  # минус дорожки и площадки

        return [
            {
                "type": "lawn",
                "name": "Газон (мятлик луговой)",
                "area_m2": max(0, lawn_area),
                "mowing_frequency": "1 раз в неделю",
            }
        ]

    def _design_pathways(self, lot_w, lot_l, zones, style) -> list[dict]:
        """Дорожки."""
        pathways = []

        # Главная дорожка от входа
        pathways.append(
            {
                "name": "main_path",
                "label": "Главная дорожка",
                "material": "тротуарная плитка" if style != "japanese" else "ступени из камня",
                "width": 1.2,
                "points": [
                    {"x": lot_w / 2, "y": lot_l},
                    {"x": lot_w / 2, "y": lot_l - 8},
                ],
            }
        )

        # Боковая дорожка
        pathways.append(
            {
                "name": "side_path",
                "label": "Боковая дорожка",
                "material": "гравий" if style in ("natural", "природный") else "плитка",
                "width": 0.8,
                "points": [
                    {"x": lot_w / 2, "y": lot_l - 8},
                    {"x": 3, "y": 3},
                ],
            }
        )

        return pathways

    def _design_pool(self, lot_w, lot_l, zones) -> dict:
        """Проектирование бассейна."""
        return {
            "name": "pool",
            "label": "Бассейн",
            "shape": "rectangle",
            "width": 8,
            "length": 4,
            "depth": 1.5,
            "x": 5,
            "y": 5,
            "material": "бетон с плиткой",
            "features": ["подсветка", "противоток", "подогрев"],
        }

    def _design_lighting(self, lot_w, lot_l, zones, style) -> list[dict]:
        """Освещение участка."""
        lights = []
        # Дорожные фонари
        for x in range(5, int(lot_w), 8):
            lights.append(
                {
                    "type": "path_light",
                    "x": x,
                    "y": lot_l - 2,
                    "height": 0.8,
                    "style": "modern" if style != "classic" else "classic",
                }
            )
        # Подсветка дома
        lights.append({"type": "wall_light", "target": "building", "warm": True})
        # Декоративная подсветка
        lights.append({"type": "spotlight", "target": "feature_tree", "warm": False})
        return lights

    def _generate_bpy_script(self, trees, shrubs, pathways, water_features, params) -> str:
        """Генерация bpy-скрипта для Blender."""
        import re as _re
        def _safe_name(s: str) -> str:
            """Sanitize name for safe use in bpy script string literals."""
            return _re.sub(r"[^a-zA-Z0-9_]", "_", str(s))

        lines = [
            "import bpy",
            "import math",
            "",
            "# === Landscape Generation ===",
            "",
            "# Ground plane",
            "bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))",
            "ground = bpy.context.active_object",
            "ground.name = 'Ground'",
            "",
        ]

        # Деревья как низкополигональные объекты
        for i, tree in enumerate(trees[:20]):  # ограничим 20 деревьями
            safe_name = _safe_name(tree.get('name', 'tree'))
            spread = float(tree.get('spread', 2))
            height = float(tree.get('height', 3))
            x = float(tree.get('x', 0))
            y = float(tree.get('y', 0))
            lines.append(f"# Tree: {safe_name}")
            lines.append(
                f"bpy.ops.mesh.primitive_cone_add(radius1={spread / 2}, depth={height}, location=({x - 15}, {y - 15}, {height / 2}))"
            )
            lines.append(f"tree_{i} = bpy.context.active_object")
            lines.append(f"tree_{i}.name = 'Tree_{safe_name}_{i}'")
            lines.append("")

        return "\n".join(lines)

    def _generate_maintenance_plan(self, trees, shrubs, groundcover) -> dict:
        """План обслуживания."""
        return {
            "spring": ["Обрезка деревьев и кустарников", "Подкормка газона", "Посадка однолетников"],
            "summer": ["Полив 2-3 раза в неделю", "Стрижка газона еженедельно", "Борьба с вредителями"],
            "autumn": ["Уборка листвы", "Подготовка растений к зиме", "Мульчирование"],
            "winter": ["Защита хвойных от снега", "Проверка освещения", "Планирование весенних работ"],
        }
