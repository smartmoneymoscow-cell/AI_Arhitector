"""
shared/agents/lighting_agent.py — Агент настройки освещения.

Отвечает за:
    - Настройку освещения под стиль/время суток
    - Расчёт естественного освещения
    - Размещение искусственных источников света
    - HDRI environment maps
    - Время суток (утро/день/вечер/ночь)
"""

import logging
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class LightingAgent(BaseAgent):
    name = "lighting"

    # Время суток → параметры освещения
    TIME_PRESETS = {
        "morning": {
            "sun_angle": 15,
            "sun_color": "#FFD4A0",
            "sun_intensity": 0.8,
            "sky_color": "#87CEEB",
            "ambient_intensity": 0.3,
            "shadow_softness": 0.7,
            "hdri": "morning_clear",
        },
        "day": {
            "sun_angle": 60,
            "sun_color": "#FFFFFF",
            "sun_intensity": 1.0,
            "sky_color": "#4169E1",
            "ambient_intensity": 0.4,
            "shadow_softness": 0.3,
            "hdri": "noon_clear",
        },
        "evening": {
            "sun_angle": 10,
            "sun_color": "#FF8C00",
            "sun_intensity": 0.6,
            "sky_color": "#FF6347",
            "ambient_intensity": 0.2,
            "shadow_softness": 0.8,
            "hdri": "sunset",
        },
        "night": {
            "sun_angle": -10,
            "sun_color": "#1C1C3B",
            "sun_intensity": 0.05,
            "sky_color": "#0A0A2A",
            "ambient_intensity": 0.1,
            "shadow_softness": 1.0,
            "hdri": "night_city",
        },
        "blue_hour": {
            "sun_angle": -5,
            "sun_color": "#4169E1",
            "sun_intensity": 0.15,
            "sky_color": "#191970",
            "ambient_intensity": 0.15,
            "shadow_softness": 0.9,
            "hdri": "blue_hour",
        },
    }

    # Типы интерьерного освещения
    INTERIOR_LIGHTING = {
        "living": [
            {"type": "ceiling", "name": "Люстра", "intensity": 0.8, "color": "#FFF8E7"},
            {"type": "floor", "name": "Торшер", "intensity": 0.4, "color": "#FFE4B5"},
            {"type": "accent", "name": "Точечная подсветка", "intensity": 0.3, "color": "#FFFFFF"},
        ],
        "kitchen": [
            {"type": "ceiling", "name": "Встраиваемые светильники", "intensity": 0.9, "color": "#FFFFFF"},
            {"type": "task", "name": "Подсветка рабочей зоны", "intensity": 1.0, "color": "#FFFFFF"},
            {"type": "accent", "name": "LED-лента под шкафами", "intensity": 0.3, "color": "#FFF8E7"},
        ],
        "bedroom": [
            {"type": "ceiling", "name": "Потолочный светильник", "intensity": 0.5, "color": "#FFE4B5"},
            {"type": "bedside", "name": "Бра", "intensity": 0.3, "color": "#FFE4B5"},
            {"type": "accent", "name": "LED-подсветка кровати", "intensity": 0.2, "color": "#FFD700"},
        ],
        "bathroom": [
            {"type": "ceiling", "name": "Влагозащищённый светильник", "intensity": 0.8, "color": "#FFFFFF"},
            {"type": "mirror", "name": "Подсветка зеркала", "intensity": 0.9, "color": "#FFFFFF"},
            {"type": "accent", "name": "Ночная подсветка", "intensity": 0.1, "color": "#4169E1"},
        ],
        "office": [
            {"type": "ceiling", "name": "Панельный светильник", "intensity": 0.9, "color": "#FFFFFF"},
            {"type": "desk", "name": "Настольная лампа", "intensity": 0.8, "color": "#FFFFFF"},
            {"type": "ambient", "name": "Бра", "intensity": 0.3, "color": "#FFF8E7"},
        ],
    }

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            lighting = self._design_lighting(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=lighting,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"LightingAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _design_lighting(self, params: dict) -> dict:
        """Проектирование освещения."""
        time_of_day = params.get("time_of_day", "day")
        style = params.get("style", "modern")
        room_type = params.get("room_type", "living")
        gen_type = params.get("gen_type", "building")

        # Освещение по времени суток
        time_preset = self.TIME_PRESETS.get(time_of_day, self.TIME_PRESETS["day"])

        # Интерьерное освещение
        interior_lights = []
        if gen_type == "interior":
            interior_lights = self.INTERIOR_LIGHTING.get(room_type, self.INTERIOR_LIGHTING["living"])

        # bpy-скрипт
        bpy_script = self._generate_bpy_script(time_preset, interior_lights, params)

        # Расчёт освещённости
        lux_calc = self._calculate_lux(interior_lights, params)

        return {
            "type": "lighting",
            "time_of_day": time_of_day,
            "sun": {
                "angle": time_preset["sun_angle"],
                "color": time_preset["sun_color"],
                "intensity": time_preset["sun_intensity"],
            },
            "sky": {
                "color": time_preset["sky_color"],
                "hdri": time_preset["hdri"],
            },
            "ambient_intensity": time_preset["ambient_intensity"],
            "shadow_softness": time_preset["shadow_softness"],
            "interior_lights": interior_lights,
            "lux_calculation": lux_calc,
            "bpy_script": bpy_script,
            "recommendations": self._generate_recommendations(time_of_day, style, room_type),
        }

    def _generate_bpy_script(self, time_preset: dict, interior_lights: list, params: dict) -> str:
        """Генерация bpy-скрипта для освещения."""
        lines = [
            "import bpy",
            "import math",
            "",
            "# === Lighting Setup ===",
            "",
            "# Sun light",
            "bpy.ops.object.light_add(type='SUN', location=(0, 0, 10))",
            "sun = bpy.context.active_object",
            f"sun.data.energy = {time_preset['sun_intensity'] * 5}",
            f"sun.rotation_euler = (math.radians({90 - time_preset['sun_angle']}), 0, 0)",
            f"sun.data.color = ({self._hex_to_rgb(time_preset['sun_color'])})",
            "",
            "# Sky / HDRI",
            f"# HDRI: {time_preset['hdri']}",
            "",
        ]

        # Interior lights
        for i, light in enumerate(interior_lights):
            light_type = "AREA" if light["type"] == "ceiling" else "POINT"
            lines.append(f"# {light['name']}")
            lines.append(f"bpy.ops.object.light_add(type='{light_type}', location=(0, 0, 3))")
            lines.append(f"light_{i} = bpy.context.active_object")
            lines.append(f"light_{i}.data.energy = {light['intensity'] * 100}")
            lines.append(f"light_{i}.data.color = ({self._hex_to_rgb(light['color'])})")
            lines.append("")

        return "\n".join(lines)

    def _calculate_lux(self, lights: list, params: dict) -> dict:
        """Расчёт освещённости (люкс)."""
        width = params.get("width_m", 6)
        length = params.get("length_m", 8)
        params.get("height_m", 3.0)
        area = width * length

        total_lumens = 0
        for light in lights:
            # Примерный расчёт: intensity * 1000 люмен
            total_lumens += light["intensity"] * 1000

        # С учётом отражения (коэфф. использования ~0.5)
        utilization = 0.5
        lux = (total_lumens * utilization) / area if area > 0 else 0

        # Нормы (СП 52.13330)
        norms = {
            "living": 150,
            "kitchen": 200,
            "bedroom": 150,
            "bathroom": 200,
            "office": 300,
            "hallway": 50,
        }
        room_type = params.get("room_type", "living")
        norm = norms.get(room_type, 150)

        return {
            "total_lumens": round(total_lumens),
            "calculated_lux": round(lux),
            "norm_lux": norm,
            "compliant": lux >= norm,
            "recommendation": "Достаточно" if lux >= norm else f"Увеличьте освещение до {norm} лк",
        }

    def _hex_to_rgb(self, hex_color: str) -> str:
        """HEX → RGB (0-1)."""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f"{r / 255:.3f}, {g / 255:.3f}, {b / 255:.3f}"

    def _generate_recommendations(self, time_of_day: str, style: str, room_type: str) -> list[str]:
        recs = []
        recs.append(f"Время суток: {time_of_day}")
        if time_of_day in ("evening", "night"):
            recs.append("Рекомендуется тёплое освещение (2700-3000K)")
        else:
            recs.append("Нейтральное освещение (4000-5000K)")

        if style in ("modern", "минимализм"):
            recs.append("Скрытое LED-освещение в нишах")
        elif style in ("классический", "baroque"):
            recs.append("Декоративные люстры и бра")

        if room_type == "bedroom":
            recs.append("Диммируемое освещение для спальни")
        elif room_type == "kitchen":
            recs.append("Яркое рабочее освещение + декоративное")

        return recs
