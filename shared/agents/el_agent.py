"""
shared/agents/el_agent.py — Агент электрики и умного дома (квартирный уровень).

Отвечает за:
    - Распознавание электрических зарисовок (фото → данные)
    - Проектирование квартирной электрики (трассы в стяжке, однолинейная схема)
    - Проектирование систем умного дома (KNX, Loxone, Zigbee)
    - Визуализацию электрощитов (3D DIN-рейки)
    - Выбор кабелей и оборудования
"""

import logging
import math
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class ELAgent(BaseAgent):
    """Квартирная электрика + умный дом + распознавание зарисовок."""

    name = "el"

    # Кабели (ВВгнг-LS по ПУЭ)
    CABLE_TYPES = {
        "lighting": {"cable": "ВВгнг-LS 3×1.5", "section_mm2": 1.5, "max_breaker_a": 10},
        "outlets": {"cable": "ВВгнг-LS 3×2.5", "section_mm2": 2.5, "max_breaker_a": 16},
        "power_4kw": {"cable": "ВВгнг-LS 3×4", "section_mm2": 4, "max_breaker_a": 25},
        "power_6kw": {"cable": "ВВгнг-LS 3×6", "section_mm2": 6, "max_breaker_a": 32},
        "three_phase": {"cable": "ВВгнг-LS 5×6", "section_mm2": 6, "max_breaker_a": 32},
    }

    # Умные дома
    SMART_HOME_SYSTEMS = {
        "knx": {
            "name": "KNX",
            "type": "проводной",
            "cable": "KNX TP 2×2×0.8",
            "cost_per_point": 35000,
            "reliability": "высокая",
            "integration": "полная",
        },
        "loxone": {
            "name": "Loxone",
            "type": "проводной",
            "cable": "Cat5e/6",
            "cost_per_point": 20000,
            "reliability": "высокая",
            "integration": "хорошая",
        },
        "zigbee": {
            "name": "Zigbee 3.0",
            "type": "беспроводной",
            "cable": "только питание 220V",
            "cost_per_point": 8000,
            "reliability": "средняя",
            "integration": "ограниченная",
        },
        "yandex": {
            "name": "Яндекс/Алиса",
            "type": "беспроводной",
            "cable": "Wi-Fi",
            "cost_per_point": 3000,
            "reliability": "низкая",
            "integration": "ограниченная",
        },
    }

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            action = params.get("action", "full_electrical")

            if action == "recognize_sketch":
                result = self._recognize_sketch(params)
            elif action == "apartment_electrical":
                result = self._design_apartment_electrical(params)
            elif action == "smart_home":
                result = self._design_smart_home(params)
            elif action == "single_line_diagram":
                result = self._generate_single_line(params)
            elif action == "panel_visualization":
                result = self._visualize_panel(params)
            else:
                result = self._full_electrical_design(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=result,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"ELAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _full_electrical_design(self, params: dict) -> dict:
        """Полное проектирование электрики."""
        electrical = self._design_apartment_electrical(params)
        smart_home = self._design_smart_home(params) if params.get("smart_home", False) else None
        panel = self._visualize_panel(electrical)

        return {
            "type": "full_electrical",
            "electrical": electrical,
            "smart_home": smart_home,
            "panel_visualization": panel,
            "total_cost_rub": (
                electrical["estimated_cost_rub"] + (smart_home["estimated_cost_rub"] if smart_home else 0)
            ),
        }

    def _design_apartment_electrical(self, params: dict) -> dict:
        """Детальное квартирная электрика: трассы, группы, кабели."""
        rooms = params.get("rooms", [])
        area_m2 = params.get("area_m2", 80)
        floors = params.get("floors", 1)

        groups = []
        group_num = 1
        total_load_w = 0

        # Группы по комнатам
        for room in rooms:
            rtype = room.get("type", "living")
            rname = room.get("name", rtype)
            rarea = room.get("area_m2", 15)

            # Освещение (LED 10 Вт/м²)
            light_load = max(5, int(rarea * 10))
            light_points = max(1, int(rarea / 5))
            groups.append(
                {
                    "group": group_num,
                    "name": f"{rname} — освещение",
                    "breaker": "B10",
                    "poles": "1P",
                    "cable": "ВВгнг-LS 3×1.5",
                    "section_mm2": 1.5,
                    "load_w": light_load,
                    "points": light_points,
                    "route": f"ЩК → РК{group_num} → выключатели/светильники",
                    "in_stяжке": True,
                }
            )
            total_load_w += light_load
            group_num += 1

            # Розетки
            outlet_count = max(2, int(rarea / 3))
            outlet_load = min(3500, outlet_count * 400)
            groups.append(
                {
                    "group": group_num,
                    "name": f"{rname} — розетки",
                    "breaker": "B16",
                    "poles": "1P",
                    "cable": "ВВгнг-LS 3×2.5",
                    "section_mm2": 2.5,
                    "load_w": outlet_load,
                    "points": outlet_count,
                    "route": f"ЩК → РК{group_num} → розетки",
                    "in_stяжке": True,
                }
            )
            total_load_w += outlet_load
            group_num += 1

        # Силовые линии
        power_lines = [
            {"name": "Электроплита", "breaker": "B32", "cable": "ВВгнг-LS 3×6", "load_w": 7000, "section": 6},
            {"name": "Духовка", "breaker": "B16", "cable": "ВВгнг-LS 3×2.5", "load_w": 2500, "section": 2.5},
            {
                "name": "Стиральная машина",
                "breaker": "B16",
                "cable": "ВВгнг-LS 3×2.5",
                "load_w": 2500,
                "section": 2.5,
                "rcd": "30mA",
            },
            {
                "name": "Посудомоечная машина",
                "breaker": "B16",
                "cable": "ВВгнг-LS 3×2.5",
                "load_w": 2000,
                "section": 2.5,
                "rcd": "30mA",
            },
            {"name": "Кондиционер", "breaker": "B16", "cable": "ВВгнг-LS 3×2.5", "load_w": 2000, "section": 2.5},
            {
                "name": "Водонагреватель",
                "breaker": "B16",
                "cable": "ВВгнг-LS 3×2.5",
                "load_w": 2500,
                "section": 2.5,
                "rcd": "30mA",
            },
        ]
        for pl in power_lines:
            groups.append(
                {
                    "group": group_num,
                    "name": pl["name"],
                    "breaker": pl["breaker"],
                    "poles": "1P",
                    "cable": pl["cable"],
                    "section_mm2": pl["section"],
                    "load_w": pl["load_w"],
                    "rcd": pl.get("rcd"),
                    "route": f"ЩК → {pl['name']}",
                }
            )
            total_load_w += pl["load_w"]
            group_num += 1

        main_breaker_a = max(25, math.ceil(total_load_w / 220))

        return {
            "total_load_w": total_load_w,
            "total_load_kw": round(total_load_w / 1000, 1),
            "main_breaker_a": main_breaker_a,
            "phases": 1 if total_load_w < 10000 else 3,
            "voltage": "220V" if total_load_w < 10000 else "380V",
            "groups": groups,
            "groups_count": len(groups),
            "grounding": "TN-C-S",
            "cable_spec": self._cable_specification(groups),
            "panel_spec": self._panel_specification(groups, main_breaker_a),
            "estimated_cost_rub": round(area_m2 * 2500),
        }

    def _design_smart_home(self, params: dict) -> dict:
        """Проектирование умного дома."""
        system = params.get("smart_home_system", "zigbee")
        rooms = params.get("rooms", [])
        area_m2 = params.get("area_m2", 80)

        sel = self.SMART_HOME_SYSTEMS.get(system, self.SMART_HOME_SYSTEMS["zigbee"])

        sensors = [
            {"type": "Датчик движения", "qty": max(2, len(rooms)), "location": "Коридор, лестница"},
            {"type": "Датчик температуры", "qty": max(1, len(rooms) // 2), "location": "Гостиная, спальня"},
            {"type": "Датчик протечки", "qty": 3, "location": "Кухня, ванная, котельная"},
            {"type": "Датчик дыма", "qty": max(2, len(rooms) // 2), "location": "Кухня, коридор"},
        ]

        actuators = [
            {"type": "Реле освещения", "qty": max(4, len(rooms) * 2), "location": "Щит"},
            {"type": "Привод штор", "qty": max(2, len(rooms) // 2), "location": "Окна"},
            {"type": "Термоголовка", "qty": max(2, len(rooms) // 2), "location": "Радиаторы"},
        ]

        scenarios = [
            {"name": "Утро", "actions": ["Открытие штор", "Включение света в кухне", "Музыка"]},
            {"name": "Уход", "actions": ["Выключение всего", "Закрытие штор", "Охрана"]},
            {"name": "Кино", "actions": ["Приглушение света", "Закрытие штор", "ТВ"]},
            {"name": "Ночь", "actions": ["Выключение всего", "Ночной свет 10%", "Охрана"]},
            {"name": "Гость", "actions": ["Приветственный свет", "Комфортная температура"]},
        ]

        total_points = sum(s["qty"] for s in sensors) + sum(a["qty"] for a in actuators)

        return {
            "system": sel,
            "sensors": sensors,
            "actuators": actuators,
            "scenarios": scenarios,
            "total_points": total_points,
            "estimated_cost_rub": round(total_points * sel["cost_per_point"] * 0.7),
        }

    def _generate_single_line(self, params: dict) -> dict:
        """Однолинейная схема электрики."""
        electrical = params.get("electrical") or self._design_apartment_electrical(params)
        groups = electrical.get("groups", [])

        diagram = {
            "main_breaker": f"QF0 — ВА47-29 — {electrical['main_breaker_a']}A — 2P",
            "rcd_main": "RCD1 — ВДТ — 63A/30мА — 2P",
            "groups": [],
        }

        for g in groups:
            line = {
                "num": g["group"],
                "name": g["name"],
                "breaker": f"{g['breaker']} {g['poles']}",
                "cable": g["cable"],
            }
            if g.get("rcd"):
                line["rcd"] = f"УЗО {g['rcd']}"
            diagram["groups"].append(line)

        return {
            "single_line_diagram": diagram,
            "format": "текстовый (для генерации DWG требуется CAD-сервис)",
        }

    def _visualize_panel(self, params: dict) -> dict:
        """Визуализация щитового оборудования."""
        if isinstance(params, dict) and "groups" in params:
            groups = params["groups"]
            main_breaker_a = params.get("main_breaker_a", 40)
        else:
            electrical = self._design_apartment_electrical(params)
            groups = electrical["groups"]
            main_breaker_a = electrical["main_breaker_a"]

        modules = []
        # Вводной автомат
        modules.append(
            {
                "position": 1,
                "type": "Автомат вводной",
                "model": f"ВА47-29 {main_breaker_a}A 2P",
                "label": "QF0",
                "poles": 2,
            }
        )
        # Реле напряжения
        modules.append(
            {
                "position": 3,
                "type": "Реле напряжения",
                "model": "Зубр РН-113",
                "label": "UV1",
                "poles": 2,
            }
        )
        # УЗО
        modules.append(
            {
                "position": 5,
                "type": "УЗО",
                "model": "ВДТ-63 30мА 2P",
                "label": "RCD1",
                "poles": 2,
            }
        )
        # Автоматы групп
        pos = 7
        for g in groups:
            modules.append(
                {
                    "position": pos,
                    "type": "Автомат группы",
                    "model": f"{g['breaker']} {g['poles']}",
                    "label": f"QF{g['group']}",
                    "poles": 1,
                    "group_name": g["name"],
                }
            )
            pos += 1

        total_modules = pos - 1
        panel_size = 24 if total_modules <= 20 else 36 if total_modules <= 32 else 48

        return {
            "panel_type": f"Щит квартирный на {panel_size} модулей",
            "total_modules_used": total_modules,
            "panel_size_modules": panel_size,
            "modules": modules,
            "busbars": [
                "N (нейтраль) — синяя шина",
                "PE (земля) — зелёно-жёлтая шина",
            ],
            "visual_description": self._panel_ascii(modules, panel_size),
        }

    def _cable_specification(self, groups: list) -> list[dict]:
        """Спецификация кабелей."""
        spec = {}
        for g in groups:
            cable = g.get("cable", "ВВгнг-LS 3×2.5")
            if cable not in spec:
                spec[cable] = {"cable": cable, "length_m": 0, "groups": []}
            spec[cable]["length_m"] += 15
            spec[cable]["groups"].append(g["name"])
        return list(spec.values())

    def _panel_specification(self, groups: list, main_breaker_a: int) -> dict:
        """Спецификация щитового оборудования."""
        modules = 2 + len(groups)
        return {
            "panel_type": f"Щит квартирный на {max(24, modules + 4)} модулей",
            "main_breaker": f"ВА47-29 — {main_breaker_a}A — 2P",
            "rcd": "ВДТ — 63A/30мА — 2P",
            "breakers": [{"group": g["name"], "type": g["breaker"]} for g in groups],
            "total_modules": modules,
        }

    def _panel_ascii(self, modules: list, panel_size: int) -> str:
        """ASCII-визуализация щита."""
        lines = [f"┌{'─' * 40}┐"]
        lines.append(f"│ Щит на {panel_size} модулей{' ' * (28 - len(str(panel_size)))}│")
        lines.append(f"├{'─' * 40}┤")
        for m in modules:
            label = f"{m['label']:6s} {m['model']}"
            lines.append(f"│ {label:38s} │")
        lines.append(f"├{'─' * 40}┤")
        lines.append(f"│ {'N (синяя)':19s} │ {'PE (зел/желт)':18s} │")
        lines.append(f"└{'─' * 40}┘")
        return "\n".join(lines)

    def _recognize_sketch(self, params: dict) -> dict:
        """Распознавание зарисовки (заглушка — требуется omni API)."""
        return {
            "status": "requires_omni_api",
            "message": "Для распознавания зарисовок требуется интеграция с mimo-omni API",
            "workflow": [
                "1. Загрузка фото/скана в чат",
                "2. mimo-omni: распознавание элементов (щиты, розетки, трассы)",
                "3. Формирование графа соединений",
                "4. Автоматическое проектирование на основе распознанных данных",
                "5. Генерация DWG-плана + однолинейной схемы",
            ],
        }
