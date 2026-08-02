"""
shared/agents/furniture_agent.py — Агент размещения мебели.

Отвечает за:
    - Эргономичное размещение мебели
    - Подбор мебели под стиль
    - Генерацию расстановки мебели
    - bpy-скрипты для мебели
"""

import logging
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class FurnitureAgent(BaseAgent):
    name = "furniture"

    # Каталог мебели по типам комнат
    FURNITURE_CATALOG = {
        "living": {
            "essential": [
                {"name": "Диван", "width": 2.2, "depth": 0.9, "height": 0.8, "clearance": 0.6},
                {"name": "Журнальный столик", "width": 1.0, "depth": 0.6, "height": 0.45, "clearance": 0.4},
                {"name": "ТВ-тумба", "width": 1.5, "depth": 0.4, "height": 0.5, "clearance": 0.3},
            ],
            "optional": [
                {"name": "Кресло", "width": 0.8, "depth": 0.8, "height": 0.9, "clearance": 0.5},
                {"name": "Стеллаж", "width": 0.8, "depth": 0.3, "height": 1.8, "clearance": 0.3},
                {"name": "Комод", "width": 1.2, "depth": 0.5, "height": 0.8, "clearance": 0.3},
            ],
        },
        "kitchen": {
            "essential": [
                {"name": "Кухонный гарнитур (L-образный)", "width": 3.0, "depth": 0.6, "height": 2.2, "clearance": 1.2},
                {"name": "Обеденный стол", "width": 1.4, "depth": 0.8, "height": 0.75, "clearance": 0.6},
                {"name": "Стул", "width": 0.45, "depth": 0.45, "height": 0.9, "clearance": 0.6, "qty": 4},
            ],
            "optional": [
                {"name": "Барная стойка", "width": 1.5, "depth": 0.5, "height": 1.1, "clearance": 0.6},
                {"name": "Остров", "width": 1.2, "depth": 0.8, "height": 0.9, "clearance": 1.2},
            ],
        },
        "bedroom": {
            "essential": [
                {"name": "Кровать двуспальная", "width": 2.0, "depth": 1.6, "height": 0.5, "clearance": 0.7},
                {"name": "Прикроватная тумба", "width": 0.5, "depth": 0.4, "height": 0.55, "clearance": 0.3, "qty": 2},
                {"name": "Шкаф-купе", "width": 2.0, "depth": 0.6, "height": 2.4, "clearance": 0.8},
            ],
            "optional": [
                {"name": "Комод", "width": 1.2, "depth": 0.5, "height": 0.8, "clearance": 0.3},
                {"name": "Туалетный столик", "width": 1.0, "depth": 0.5, "height": 0.75, "clearance": 0.6},
                {"name": "Кресло", "width": 0.7, "depth": 0.7, "height": 0.9, "clearance": 0.5},
            ],
        },
        "bathroom": {
            "essential": [
                {"name": "Ванна", "width": 1.7, "depth": 0.75, "height": 0.6, "clearance": 0.7},
                {"name": "Унитаз", "width": 0.4, "depth": 0.7, "height": 0.4, "clearance": 0.2},
                {"name": "Умывальник с тумбой", "width": 0.6, "depth": 0.45, "height": 0.85, "clearance": 0.7},
            ],
            "optional": [
                {"name": "Душевая кабина", "width": 0.9, "depth": 0.9, "height": 2.0, "clearance": 0.8},
                {"name": "Полотенцесушитель", "width": 0.5, "depth": 0.1, "height": 1.2, "clearance": 0.2},
            ],
        },
        "office": {
            "essential": [
                {"name": "Рабочий стол", "width": 1.4, "depth": 0.7, "height": 0.75, "clearance": 1.0},
                {"name": "Офисное кресло", "width": 0.65, "depth": 0.65, "height": 1.2, "clearance": 0.8},
                {"name": "Шкаф для документов", "width": 0.9, "depth": 0.45, "height": 1.8, "clearance": 0.6},
            ],
            "optional": [
                {"name": "Книжный стеллаж", "width": 1.2, "depth": 0.35, "height": 2.0, "clearance": 0.3},
                {
                    "name": "Зона для встреч (стол + 4 стула)",
                    "width": 1.8,
                    "depth": 0.9,
                    "height": 0.75,
                    "clearance": 0.8,
                },
            ],
        },
    }

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            layout = self._arrange_furniture(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=layout,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"FurnitureAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _arrange_furniture(self, params: dict) -> dict:
        """Расставить мебель в комнате."""
        room_type = params.get("room_type", "living")
        width = params.get("width_m", 6)
        length = params.get("length_m", 8)
        height = params.get("height_m", 3.0)
        style = params.get("style", "modern")
        include_optional = params.get("include_optional", False)

        area = width * length
        catalog = self.FURNITURE_CATALOG.get(room_type, self.FURNITURE_CATALOG["living"])

        # Подбираем мебель
        selected = list(catalog["essential"])
        if include_optional:
            selected.extend(catalog["optional"])

        # Размещаем мебель
        placements = self._place_items(selected, width, length)

        # Проверяем эргономику
        ergonomics = self._check_ergonomics(placements, width, length)

        # Генерируем bpy-скрипт
        bpy_script = self._generate_bpy_script(placements, style, height)

        # Статистика
        total_furniture_area = sum(item["width"] * item["depth"] * item.get("qty", 1) for item in selected)
        floor_area = area
        furniture_ratio = total_furniture_area / floor_area * 100 if floor_area > 0 else 0

        return {
            "type": "furniture_layout",
            "room_type": room_type,
            "room_dimensions": {"width": width, "length": length, "area": area},
            "furniture_count": len(placements),
            "placements": placements,
            "ergonomics": ergonomics,
            "space_utilization_pct": round(furniture_ratio, 1),
            "free_space_pct": round(100 - furniture_ratio, 1),
            "bpy_script": bpy_script,
            "style_advice": self._style_advice(style, room_type),
        }

    def _place_items(self, items: list, room_w: float, room_l: float) -> list[dict]:
        """Разместить предметы мебели."""
        placements = []
        x_cursor = 0.3  # отступ от стены
        y_cursor = 0.3

        for item in items:
            qty = item.get("qty", 1)
            for q in range(qty):
                placement = {
                    "name": item["name"],
                    "x": round(x_cursor, 2),
                    "y": round(y_cursor, 2),
                    "width": item["width"],
                    "depth": item["depth"],
                    "height": item["height"],
                    "rotation": 0,
                }

                # Простая стратегия: вдоль стены
                x_cursor += item["width"] + item["clearance"]
                if x_cursor + item["width"] > room_w - 0.3:
                    x_cursor = 0.3
                    y_cursor += item["depth"] + item["clearance"]

                placements.append(placement)

        return placements

    def _check_ergonomics(self, placements: list, room_w: float, room_l: float) -> dict:
        """Проверка эргономики расстановки."""
        issues = []
        warnings = []

        # Проверяем, что мебель не выходит за пределы комнаты
        for p in placements:
            if p["x"] + p["width"] > room_w:
                issues.append(f"❌ {p['name']} выходит за правую стену")
            if p["y"] + p["depth"] > room_l:
                issues.append(f"❌ {p['name']} выходит за заднюю стену")

        # Проверяем проходы
        for i, p1 in enumerate(placements):
            for j, p2 in enumerate(placements):
                if i >= j:
                    continue
                dx = abs(p1["x"] - p2["x"])
                dy = abs(p1["y"] - p2["y"])
                min_gap = 0.6  # мин. проход
                if dx < min_gap and dy < min_gap:
                    warnings.append(f"⚠️ {p1['name']} и {p2['name']} слишком близко")

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "clearance_ok": len(warnings) == 0,
        }

    def _generate_bpy_script(self, placements: list, style: str, room_height: float) -> str:
        """Генерация bpy-скрипта для мебели."""
        lines = [
            "import bpy",
            "",
            "# === Furniture Layout ===",
            "",
        ]

        for i, p in enumerate(placements):
            name_safe = p["name"].replace(" ", "_").replace("(", "").replace(")", "")
            lines.append(f"# {p['name']}")
            lines.append(
                f"bpy.ops.mesh.primitive_cube_add("
                f"size=1, "
                f"location=({p['x'] + p['width'] / 2}, {p['y'] + p['depth'] / 2}, {p['height'] / 2}))"
            )
            lines.append(f"obj_{i} = bpy.context.active_object")
            lines.append(f"obj_{i}.name = '{name_safe}_{i}'")
            lines.append(f"obj_{i}.scale = ({p['width'] / 2}, {p['depth'] / 2}, {p['height'] / 2})")
            lines.append("")

        return "\n".join(lines)

    def _style_advice(self, style: str, room_type: str) -> list[str]:
        """Рекомендации по стилю."""
        advice = {
            "modern": ["Мебель с прямыми линиями", "Нейтральные цвета", "Минимум декора"],
            "классический": ["Деревянная мебель с резьбой", "Ткани с узором", "Антикварные элементы"],
            "лофт": ["Металл + дерево", "Открытые полки", "Индустриальные акценты"],
            "минимализм": ["Встроенная мебель", "Скрытые ручки", "Монохром"],
            "скандинавский": ["Светлое дерево", "Текстиль", "Растения"],
        }
        return advice.get(style, advice["modern"])
