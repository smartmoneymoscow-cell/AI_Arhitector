"""
shared/agents/mep_agent.py — Агент инженерных систем (MEP).

Отвечает за:
    - Проектирование электрики
    - Проектирование водоснабжения и канализации
    - Проектирование вентиляции и кондиционирования (HVAC)
    - Проектирование отопления
    - Слаботочные системы (связь, безопасность)
"""

import logging
import math
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class MEPAgent(BaseAgent):
    name = "mep"

    # Нормы потребления
    ELECTRICAL_LOADS = {
        "living": 150,  # Вт/м²
        "kitchen": 300,
        "bedroom": 100,
        "bathroom": 150,
        "office": 200,
        "hallway": 50,
    }

    WATER_DEMAND = {
        "house": 300,  # литров/сутки на человека
        "apartment": 200,
        "office": 50,
    }

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            system = params.get("system", "all")

            if system == "electrical":
                result = self._design_electrical(params)
            elif system == "plumbing":
                result = self._design_plumbing(params)
            elif system == "hvac":
                result = self._design_hvac(params)
            elif system == "low_voltage":
                result = self._design_low_voltage(params)
            else:
                result = self._design_all(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=result,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"MEPAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _design_all(self, params: dict) -> dict:
        """Проектирование всех инженерных систем."""
        return {
            "type": "mep_full",
            "electrical": self._design_electrical(params),
            "plumbing": self._design_plumbing(params),
            "hvac": self._design_hvac(params),
            "low_voltage": self._design_low_voltage(params),
            "summary": self._generate_summary(params),
        }

    def _design_electrical(self, params: dict) -> dict:
        """Проектирование электрики."""
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)
        floors = params.get("floors", 1)
        rooms = params.get("rooms", [])

        total_area = width * length * floors

        # Расчёт нагрузки
        total_load = 0
        room_details = []

        if rooms:
            for room in rooms:
                rtype = room.get("type", "living")
                rarea = room.get("width", 3) * room.get("length", 4)
                load = self.ELECTRICAL_LOADS.get(rtype, 150) * rarea
                total_load += load
                room_details.append(
                    {
                        "room": rtype,
                        "area_m2": round(rarea, 1),
                        "load_w": round(load),
                        "outlets": max(2, int(rarea / 3)),
                        "lighting": max(1, int(rarea / 5)),
                    }
                )
        else:
            total_load = 150 * total_area

        # Вводной щит
        main_breaker = math.ceil(total_load / 220)  # Ампер
        main_breaker = max(main_breaker, 25)

        # Группы
        groups = self._create_electrical_groups(room_details or [{"room": "general", "load_w": total_load}])

        return {
            "total_load_w": round(total_load),
            "total_load_kw": round(total_load / 1000, 1),
            "main_breaker_a": main_breaker,
            "voltage": "220V/380V",
            "phases": 3 if total_load > 10000 else 1,
            "groups": groups,
            "room_details": room_details,
            "grounding": "TN-C-S",
            "cable_type": "ВВГнг-LS",
            "estimated_cost": round(total_area * 1500),  # руб
        }

    def _design_plumbing(self, params: dict) -> dict:
        """Проектирование водоснабжения и канализации."""
        floors = params.get("floors", 1)
        building_type = params.get("building_type", "house")
        occupants = params.get("occupants", 4)

        daily_demand = self.WATER_DEMAND.get(building_type, 300) * occupants

        # Трубопроводы
        cold_pipe = "Ду 25" if occupants <= 4 else "Ду 32"
        hot_pipe = "Ду 20" if occupants <= 4 else "Ду 25"

        # Канализация
        sewer_pipe = "Ду 110" if floors > 1 else "Ду 50"

        return {
            "daily_demand_liters": daily_demand,
            "peak_flow_m3h": round(daily_demand * 0.1 / 1000, 2),
            "cold_water": {
                "pipe": cold_pipe,
                "material": "ППР (полипропилен)",
                "pressure": "3-6 бар",
                "source": "Магистраль / скважина",
            },
            "hot_water": {
                "pipe": hot_pipe,
                "material": "ППР (полипропилен)",
                "heater": "Бойлер косвенного нагрева" if occupants > 3 else "Проточный нагреватель",
                "volume_liters": occupants * 50,
            },
            "sewerage": {
                "pipe": sewer_pipe,
                "material": "ПВХ",
                "type": "Самотёчная" if floors <= 2 else "С напорным участком",
                "treatment": "Септик" if building_type in ("house", "cottage") else "Централизованная",
            },
            "estimated_cost": round(occupants * 15000 + floors * 25000),
        }

    def _design_hvac(self, params: dict) -> dict:
        """Проектирование вентиляции и кондиционирования."""
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)
        height = params.get("height_m", 3.0)
        floors = params.get("floors", 1)

        volume = width * length * height * floors
        air_exchange = volume * 1.0  # 1 объём в час

        # Тепловая мощность
        heat_load = volume * 40  # ~40 Вт/м³ для Москвы

        return {
            "ventilation": {
                "type": "Приточно-вытяжная с рекуперацией",
                "air_flow_m3h": round(air_exchange),
                "heat_recovery_pct": 80,
                "duct_type": "Круглые / прямоугольные",
                "filter_class": "F7 / G4",
            },
            "cooling": {
                "type": "Сплит-система" if floors <= 2 else "Мульти-сплит",
                "capacity_kw": round(heat_load / 1000 * 0.8, 1),
                "indoor_units": floors * 2,
                "refrigerant": "R-32",
            },
            "heating": {
                "type": "Водяное отопление",
                "heat_load_kw": round(heat_load / 1000, 1),
                "radiators": "Алюминиевые секционные",
                "boiler": "Газовый конденсационный" if heat_load < 50000 else "Твердотопливный",
            },
            "estimated_cost": round(volume * 2000),
        }

    def _design_low_voltage(self, params: dict) -> dict:
        """Слаботочные системы."""
        return {
            "network": {
                "type": "Структурированная кабельная система",
                "cable": "Cat 6A UTP",
                "access_points": max(1, int(params.get("width_m", 10) * params.get("length_m", 10) / 50)),
                "switch": "PoE для камер и точек доступа",
            },
            "security": {
                "cameras": max(4, params.get("floors", 1) * 4),
                "type": "IP камеры 4K",
                "nvr": "8-канальный NVR",
                "storage_days": 30,
                "alarm": "Охранная сигнализация с GSM-модулем",
            },
            "fire_safety": {
                "detectors": "Дымовые + тепловые",
                "notification": "Сирена + световая",
                "monitoring": "Подключение к пульту охраны",
            },
            "smart_home": {
                "protocol": "Zigbee 3.0 / Matter",
                "controller": "Центральный хаб",
                "features": ["Управление освещением", "Климат-контроль", "Безопасность", "Шторы"],
            },
            "estimated_cost": round(params.get("width_m", 10) * params.get("length_m", 10) * 800),
        }

    # ═══ Расширения: квартирная электрика, умный дом, зарисовки ═══

    def design_apartment_electrical(self, params: dict) -> dict:
        """Детальное проектирование квартирной электрики (трассы в стяжке)."""
        rooms = params.get("rooms", [])
        total_area = params.get("area_m2", 80)

        # Расчёт нагрузок по группам
        groups = []
        group_num = 1
        total_load_w = 0

        for room in rooms:
            rtype = room.get("type", "living")
            rarea = room.get("area_m2", 15)

            # Освещение (LED)
            light_load = max(5, int(rarea * 10))  # 10 Вт/м² LED
            light_outlets = max(1, int(rarea / 5))
            groups.append(
                {
                    "group": group_num,
                    "name": f"{rtype} — освещение",
                    "breaker_type": "B10",
                    "breaker_poles": "1P",
                    "cable": "ВВГнг-LS 3×1.5",
                    "cable_section_mm2": 1.5,
                    "load_w": light_load,
                    "points": light_outlets,
                    "route": f"ЩК → РК{group_num} → выключатели/светильники",
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
                    "name": f"{rtype} — розетки",
                    "breaker_type": "B16",
                    "breaker_poles": "1P",
                    "cable": "ВВГнг-LS 3×2.5",
                    "cable_section_mm2": 2.5,
                    "load_w": outlet_load,
                    "points": outlet_count,
                    "route": f"ЩК → РК{group_num} → розетки",
                }
            )
            total_load_w += outlet_load
            group_num += 1

        # Силовые группы (отдельные линии)
        power_groups = [
            {"name": "Электроплита", "breaker": "B32", "cable": "ВВГнг-LS 3×6", "load_w": 7000, "rcd": "30mA"},
            {"name": "Духовка", "breaker": "B16", "cable": "ВВГнг-LS 3×2.5", "load_w": 2500},
            {"name": "Стиральная машина", "breaker": "B16", "cable": "ВВГнг-LS 3×2.5", "load_w": 2500, "rcd": "30mA"},
            {
                "name": "Посудомоечная машина",
                "breaker": "B16",
                "cable": "ВВГнг-LS 3×2.5",
                "load_w": 2000,
                "rcd": "30mA",
            },
            {"name": "Кондиционер", "breaker": "B16", "cable": "ВВГнг-LS 3×2.5", "load_w": 2000},
            {"name": "Водонагреватель", "breaker": "B16", "cable": "ВВГнг-LS 3×2.5", "load_w": 2500, "rcd": "30mA"},
        ]
        for pg in power_groups:
            groups.append(
                {
                    "group": group_num,
                    "name": pg["name"],
                    "breaker_type": pg["breaker"],
                    "breaker_poles": "1P",
                    "cable": pg["cable"],
                    "load_w": pg["load_w"],
                    "rcd": pg.get("rcd"),
                }
            )
            total_load_w += pg["load_w"]
            group_num += 1

        # Вводной щит
        main_breaker_a = max(25, math.ceil(total_load_w / 220))

        # Однолинейная схема (текстовая)
        single_line = {
            "main_breaker": f"QF0 — ВА47-29 — {main_breaker_a}A — 2P",
            "rcd_main": "RCD1 — ВДТ — 63A/30мА — 2P (если не дифавтоматы)",
            "groups": [
                {"num": g["group"], "name": g["name"], "breaker": g["breaker_type"], "cable": g["cable"]}
                for g in groups
            ],
        }

        return {
            "total_load_w": total_load_w,
            "total_load_kw": round(total_load_w / 1000, 1),
            "main_breaker_a": main_breaker_a,
            "phases": 1 if total_load_w < 10000 else 3,
            "voltage": "220V" if total_load_w < 10000 else "380V",
            "groups": groups,
            "groups_count": len(groups),
            "single_line_diagram": single_line,
            "cable_spec": self._generate_cable_spec(groups),
            "panel_spec": self._generate_panel_spec(groups, main_breaker_a),
            "grounding": "TN-C-S",
            "estimated_cost_rub": round(total_area * 2500),
        }

    def design_smart_home(self, params: dict) -> dict:
        """Проектирование системы умного дома."""
        system = params.get("smart_home_system", "zigbee")
        rooms = params.get("rooms", [])
        area_m2 = params.get("area_m2", 80)
        budget = params.get("smart_home_budget", "medium")

        systems = {
            "knx": {
                "name": "KNX",
                "type": "проводной",
                "cable": "KNX TP 2×2×0.8",
                "cost_per_point": 35000,
                "reliability": "высокая",
                "features": ["Полная интеграция", "Промышленная надёжность", "Масштабируемость"],
            },
            "loxone": {
                "name": "Loxone",
                "type": "проводной",
                "cable": "Cat5e/6",
                "cost_per_point": 20000,
                "reliability": "высокая",
                "features": ["Компактный контроллер", "Красивый UI", "Средняя цена"],
            },
            "zigbee": {
                "name": "Zigbee 3.0",
                "type": "беспроводной",
                "cable": "только питание 220V",
                "cost_per_point": 8000,
                "reliability": "средняя",
                "features": ["Дёшево", "Не нужно штробить", "Ограниченный функционал"],
            },
            "yandex": {
                "name": "Яндекс/Алиса",
                "type": "беспроводной",
                "cable": "Wi-Fi",
                "cost_per_point": 3000,
                "reliability": "низкая",
                "features": ["Голосовое управление", "Бюджетно", "Очень ограниченный функционал"],
            },
        }
        sel = systems.get(system, systems["zigbee"])

        # Датчики
        sensors = [
            {"type": "Датчик движения", "qty": max(2, len(rooms)), "location": "Коридор, лестница"},
            {"type": "Датчик температуры", "qty": max(1, len(rooms) // 2), "location": "Гостиная, спальня"},
            {"type": "Датчик протечки", "qty": 3, "location": "Кухня, ванная, котельная"},
            {"type": "Датчик дыма", "qty": max(2, len(rooms) // 2), "location": "Кухня, коридор"},
            {"type": "Датчик открытия двери", "qty": 2, "location": "Входная дверь, балкон"},
        ]

        # Актуаторы
        actuators = [
            {"type": "Реле освещения", "qty": max(4, len(rooms) * 2), "location": "Щит"},
            {"type": "Привод штор", "qty": max(2, len(rooms) // 2), "location": "Окна"},
            {"type": "Термоголовка", "qty": max(2, len(rooms) // 2), "location": "Радиаторы"},
        ]

        # Сценарии
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
            "estimated_cost_rub": round(total_points * sel["cost_per_point"] * 0.7),  # с оптом
            "cable_routing": self._smart_home_cable_routing(sel, rooms),
        }

    def recognize_sketch(self, image_data: dict) -> dict:
        """Распознавание электрической зарисовки (заглушка — требуется omni API)."""
        # В реальной реализации: mimo-omni API для распознавания
        return {
            "status": "requires_omni_api",
            "message": "Для распознавания зарисовок требуется интеграция с mimo-omni API",
            "detected_elements": [],
            "graph": {},
        }

    def _generate_cable_spec(self, groups: list) -> list[dict]:
        """Спецификация кабелей."""
        spec = {}
        for g in groups:
            cable = g.get("cable", "ВВгнг-LS 3×2.5")
            if cable not in spec:
                spec[cable] = {"cable": cable, "length_m": 0, "groups": []}
            spec[cable]["length_m"] += 15  # Примерная длина трассы
            spec[cable]["groups"].append(g["name"])
        return list(spec.values())

    def _generate_panel_spec(self, groups: list, main_breaker_a: int) -> dict:
        """Спецификация щитового оборудования."""
        modules = 2 + len(groups)  # вводной + УЗО + автоматы
        return {
            "panel_type": f"Щит квартирный на {max(24, modules + 4)} модулей",
            "main_breaker": f"ВА47-29 — {main_breaker_a}A — 2P",
            "rcd": "ВДТ — 63A/30мА — 2P",
            "breakers": [{"group": g["name"], "type": g["breaker_type"]} for g in groups],
            "busbars": ["N (нейтраль) — синяя", "PE (земля) — зелёно-жёлтая"],
            "total_modules": modules,
        }

    def _smart_home_cable_routing(self, system: dict, rooms: list) -> list[dict]:
        """Трассы кабелей умного дома."""
        if system["type"] == "беспроводной":
            return [{"note": "Только питание 220V для актуаторов в щите"}]
        routes = []
        for room in rooms:
            routes.append(
                {
                    "from": "Щит УД",
                    "to": room.get("name", "комната"),
                    "cable": system["cable"],
                    "note": f"Отдельная трасса от силовых (≥50мм)",
                }
            )
        return routes

    def _create_electrical_groups(self, rooms: list) -> list[dict]:
        """Создать электрические группы."""
        groups = []
        group_num = 1

        for room in rooms:
            rtype = room.get("room", "general")
            load = room.get("load_w", 1500)

            # Освещение
            groups.append(
                {
                    "group": group_num,
                    "name": f"{rtype} — освещение",
                    "breaker": 10,
                    "cable": "ВВГнг-LS 3×1.5",
                    "load_w": round(load * 0.3),
                }
            )
            group_num += 1

            # Розетки
            groups.append(
                {
                    "group": group_num,
                    "name": f"{rtype} — розетки",
                    "breaker": 16,
                    "cable": "ВВГнг-LS 3×2.5",
                    "load_w": round(load * 0.7),
                }
            )
            group_num += 1

        # Отдельные группы
        groups.append(
            {"group": group_num, "name": "Электроплита", "breaker": 32, "cable": "ВВГнг-LS 3×6", "load_w": 7000}
        )
        groups.append(
            {
                "group": group_num + 1,
                "name": "Стиральная машина",
                "breaker": 16,
                "cable": "ВВГнг-LS 3×2.5",
                "load_w": 2500,
            }
        )
        groups.append(
            {
                "group": group_num + 2,
                "name": "Розетки ванная",
                "breaker": 16,
                "cable": "ВВГнг-LS 3×2.5",
                "load_w": 2000,
                "rCD": "30mA",
            }
        )

        return groups

    def _generate_summary(self, params: dict) -> dict:
        total_area = params.get("width_m", 10) * params.get("length_m", 10) * params.get("floors", 1)
        return {
            "total_systems": 4,
            "estimated_total_cost": round(total_area * 6000),
            "cost_per_m2": 6000,
            "implementation_time_weeks": max(4, int(total_area / 30)),
        }
