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
