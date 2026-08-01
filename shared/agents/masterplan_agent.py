"""
shared/agents/masterplan_agent.py — Агент генерации мастер-плана участка.

Отвечает за:
    - Генерацию мастер-плана земельного участка
    - Размещение зданий на участке
    - Планировку дорог и проездов
    - Зонирование территории
    - Расчёт площадей и отступов
"""

import time
import math
import logging
from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class MasterplanAgent(BaseAgent):
    name = "masterplan"

    # Нормативные отступы (м)
    SETBACK_FRONT = 5.0      # Отступ от красной линии
    SETBACK_SIDE = 3.0       # Боковой отступ
    SETBACK_REAR = 3.0       # Задний отступ
    MIN_ROAD_WIDTH = 3.5     # Мин. ширина проезда
    FIRE_DISTANCE = 8.0      # Расстояние для пожарного проезда

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            masterplan = self._generate_masterplan(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=masterplan,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"MasterplanAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _generate_masterplan(self, params: dict) -> dict:
        """Генерация мастер-плана."""
        lot_width = params.get("lot_width_m", 30)
        lot_length = params.get("lot_length_m", 40)
        building_width = params.get("width_m", 10)
        building_length = params.get("length_m", 12)
        building_type = params.get("building_type", "house")
        has_garage = params.get("has_garage", True)
        has_garden = params.get("has_garden", True)
        has_pool = params.get("has_pool", False)
        orientation = params.get("orientation", "north")  # Ориентация входа

        lot_area = lot_width * lot_length
        building_area = building_width * building_length

        # Оптимальное размещение здания
        building_position = self._calculate_position(
            lot_width, lot_length, building_width, building_length, orientation
        )

        # Зонирование
        zones = self._create_zones(
            lot_width, lot_length, building_position,
            building_width, building_length, has_garage, has_garden, has_pool
        )

        # Дороги и проезды
        roads = self._plan_roads(lot_width, lot_length, building_position)

        # Озеленение
        greenery = self._plan_greenery(lot_width, lot_length, zones)

        # Расчёт площадей
        area_calc = self._calculate_areas(lot_area, building_area, zones)

        return {
            "type": "masterplan",
            "lot": {
                "width": lot_width,
                "length": lot_length,
                "area_m2": lot_area,
                "orientation": orientation,
            },
            "building_position": building_position,
            "zones": zones,
            "roads": roads,
            "greenery": greenery,
            "area_calculation": area_calc,
            "setbacks": {
                "front": self.SETBACK_FRONT,
                "side": self.SETBACK_SIDE,
                "rear": self.SETBACK_REAR,
            },
            "compliance": self._check_compliance(lot_width, lot_length, building_position,
                                                  building_width, building_length),
            "svg": self._generate_svg(lot_width, lot_length, building_position,
                                       building_width, building_length, zones),
        }

    def _calculate_position(self, lot_w, lot_l, bld_w, bld_l, orientation) -> dict:
        """Рассчитать оптимальную позицию здания."""
        # С учётом отступов
        min_x = self.SETBACK_SIDE
        max_x = lot_w - bld_w - self.SETBACK_SIDE
        min_y = self.SETBACK_REAR
        max_y = lot_l - bld_l - self.SETBACK_FRONT

        # Центрируем
        x = (min_x + max_x) / 2
        y = min_y  # ближе к задней границе — больше места для сада спереди

        # Ориентация
        if orientation in ("south", "юг"):
            y = max_y  # ближе к передней границе
        elif orientation in ("east", "восток"):
            x = max_x
        elif orientation in ("west", "запад"):
            x = min_x

        return {
            "x": round(x, 1),
            "y": round(y, 1),
            "width": bld_w,
            "length": bld_l,
            "rotation": 0,
            "distance_to_front": round(lot_l - y - bld_l, 1),
            "distance_to_rear": round(y, 1),
            "distance_to_left": round(x, 1),
            "distance_to_right": round(lot_w - x - bld_w, 1),
        }

    def _create_zones(self, lot_w, lot_l, pos, bld_w, bld_l,
                       has_garage, has_garden, has_pool) -> list[dict]:
        """Зонирование участка."""
        zones = []

        # Зона застройки
        zones.append({
            "name": "building",
            "label": "Здание",
            "x": pos["x"], "y": pos["y"],
            "width": bld_w, "height": bld_l,
            "color": "#E74C3C",
        })

        # Входная зона
        zones.append({
            "name": "entrance",
            "label": "Входная зона",
            "x": pos["x"], "y": pos["y"] + bld_l,
            "width": bld_w, "height": min(5, lot_l - pos["y"] - bld_l),
            "color": "#F39C12",
        })

        # Гараж
        if has_garage:
            garage_w = min(6, lot_w - pos["x"] - bld_w - 1)
            if garage_w >= 3:
                zones.append({
                    "name": "garage",
                    "label": "Гараж",
                    "x": pos["x"] + bld_w + 1, "y": pos["y"],
                    "width": garage_w, "height": 6,
                    "color": "#95A5A6",
                })

        # Сад
        if has_garden:
            garden_x = 0
            garden_y = 0
            garden_w = lot_w
            garden_l = pos["y"] - self.SETBACK_REAR
            if garden_l > 3:
                zones.append({
                    "name": "garden",
                    "label": "Сад",
                    "x": garden_x, "y": garden_y,
                    "width": garden_w, "height": garden_l,
                    "color": "#27AE60",
                })

        # Бассейн
        if has_pool:
            pool_w = min(8, lot_w * 0.3)
            pool_l = min(4, lot_l * 0.1)
            zones.append({
                "name": "pool",
                "label": "Бассейн",
                "x": self.SETBACK_SIDE, "y": self.SETBACK_REAR,
                "width": pool_w, "height": pool_l,
                "color": "#3498DB",
            })

        # Парковка
        zones.append({
            "name": "parking",
            "label": "Парковка",
            "x": pos["x"], "y": pos["y"] + bld_l + 2,
            "width": min(bld_w, 12), "height": 3,
            "color": "#7F8C8D",
        })

        return zones

    def _plan_roads(self, lot_w, lot_l, pos) -> list[dict]:
        """Планировка дорог."""
        roads = []
        # Подъездная дорога от входа
        roads.append({
            "name": "main_access",
            "label": "Подъезд",
            "start": {"x": pos["x"] + pos["width"] / 2, "y": lot_l},
            "end": {"x": pos["x"] + pos["width"] / 2, "y": pos["y"] + pos["length"]},
            "width": self.MIN_ROAD_WIDTH,
        })
        return roads

    def _plan_greenery(self, lot_w, lot_l, zones) -> list[dict]:
        """Планировка озеленения."""
        greenery = []
        # Деревья по периметру
        tree_spacing = 4.0
        for x in range(int(self.SETBACK_SIDE), int(lot_w - self.SETBACK_SIDE), int(tree_spacing)):
            greenery.append({
                "type": "tree",
                "x": x, "y": self.SETBACK_REAR / 2,
                "radius": 1.5,
                "species": "deciduous",
            })
        return greenery

    def _calculate_areas(self, lot_area, building_area, zones) -> dict:
        """Расчёт площадей."""
        green_area = sum(z["width"] * z["height"] for z in zones if z["name"] in ("garden", "pool"))
        paved_area = sum(z["width"] * z["height"] for z in zones if z["name"] in ("parking", "entrance"))

        return {
            "lot_area_m2": lot_area,
            "building_area_m2": building_area,
            "building_coverage": round(building_area / lot_area * 100, 1),
            "green_area_m2": round(green_area, 1),
            "green_coverage": round(green_area / lot_area * 100, 1),
            "paved_area_m2": round(paved_area, 1),
            "free_area_m2": round(lot_area - building_area - green_area - paved_area, 1),
        }

    def _check_compliance(self, lot_w, lot_l, pos, bld_w, bld_l) -> dict:
        """Проверка соответствия нормам."""
        checks = []

        # Отступы
        setbacks = {
            "front": lot_l - pos["y"] - bld_l,
            "rear": pos["y"],
            "left": pos["x"],
            "right": lot_w - pos["x"] - bld_w,
        }

        if setbacks["front"] < self.SETBACK_FRONT:
            checks.append(f"❌ Отступ спереди {setbacks['front']}м < {self.SETBACK_FRONT}м")
        if setbacks["rear"] < self.SETBACK_REAR:
            checks.append(f"❌ Отступ сзади {setbacks['rear']}м < {self.SETBACK_REAR}м")
        if setbacks["left"] < self.SETBACK_SIDE:
            checks.append(f"❌ Отступ слева {setbacks['left']}м < {self.SETBACK_SIDE}м")
        if setbacks["right"] < self.SETBACK_SIDE:
            checks.append(f"❌ Отступ справа {setbacks['right']}м < {self.SETBACK_SIDE}м")

        if not checks:
            checks.append("✅ Все отступы соответствуют нормам")

        # Площадь застройки
        coverage = (bld_w * bld_l) / (lot_w * lot_l) * 100
        if coverage > 40:
            checks.append(f"⚠️ Площадь застройки {coverage:.0f}% > рекомендуемых 40%")
        else:
            checks.append(f"✅ Площадь застройки {coverage:.0f}% (норма ≤40%)")

        return {
            "passed": not any("❌" in c for c in checks),
            "setbacks": {k: round(v, 1) for k, v in setbacks.items()},
            "checks": checks,
        }

    def _generate_svg(self, lot_w, lot_l, pos, bld_w, bld_l, zones) -> str:
        """Генерация SVG плана участка."""
        scale = 10
        svg_w = lot_w * scale
        svg_l = lot_l * scale

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_l}" '
            f'width="{svg_w}" height="{svg_l}">',
            f'<rect x="0" y="0" width="{svg_w}" height="{svg_l}" fill="#F5F5DC" stroke="#333" stroke-width="2"/>',
        ]

        for zone in zones:
            x = zone["x"] * scale
            y = (lot_l - zone["y"] - zone["height"]) * scale
            w = zone["width"] * scale
            h = zone["height"] * scale
            color = zone.get("color", "#CCC")
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
                f'fill="{color}" fill-opacity="0.5" stroke="#333" stroke-width="1"/>'
            )
            # Label
            svg_parts.append(
                f'<text x="{x + w/2}" y="{y + h/2}" text-anchor="middle" '
                f'font-size="10" fill="#333">{zone.get("label", zone["name"])}</text>'
            )

        svg_parts.append('</svg>')
        return "\n".join(svg_parts)
