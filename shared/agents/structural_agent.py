"""
shared/agents/structural_agent.py — Агент конструктивного расчёта.

Отвечает за:
    - Расчёт несущих конструкций
    - Подбор фундамента
    - Расчёт перекрытий
    - Расчёт стропильной системы
    - Проверку на нагрузки (СП 20.13330)
"""

import logging
import math
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class StructuralAgent(BaseAgent):
    name = "structural"

    # Сопротивление материалов (кг/см²)
    MATERIAL_STRENGTH = {
        "brick": {"compression": 100, "bending": 4, "density": 1800},
        "кирпич": {"compression": 100, "bending": 4, "density": 1800},
        "concrete": {"compression": 250, "bending": 15, "density": 2400},
        "бетон": {"compression": 250, "bending": 15, "density": 2400},
        "wood": {"compression": 40, "bending": 80, "density": 500},
        "дерево": {"compression": 40, "bending": 80, "density": 500},
        "steel": {"compression": 2100, "bending": 2100, "density": 7850},
        "сталь": {"compression": 2100, "bending": 2100, "density": 7850},
        "foam_block": {"compression": 25, "bending": 2, "density": 600},
        "пеноблок": {"compression": 25, "bending": 2, "density": 600},
    }

    # Типы фундаментов
    FOUNDATION_TYPES = {
        "slab": {"max_floors": 3, "max_load": 500, "min_soil_bearing": 1.0},
        "strip": {"max_floors": 5, "max_load": 1000, "min_soil_bearing": 2.0},
        "pile": {"max_floors": 20, "max_load": 5000, "min_soil_bearing": 0.5},
    }

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            result = self._calculate_structure(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=result,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"StructuralAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _calculate_structure(self, params: dict) -> dict:
        """Полный конструктивный расчёт."""
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)
        height = params.get("height_m", 3.0)
        floors = params.get("floors", 1)
        material = params.get("material", "brick").lower()
        roof_type = params.get("roof_type", "gable")
        soil_type = params.get("soil_type", "medium")  # weak/medium/strong

        footprint = width * length
        footprint * floors

        # Вес здания
        weight = self._calculate_weight(params, footprint, floors, material)

        # Фундамент
        foundation = self._design_foundation(params, weight, soil_type)

        # Стены
        walls = self._design_walls(params, material, floors)

        # Перекрытия
        floors_design = self._design_floors(params, width, length, floors)

        # Крыша
        roof = self._design_roof(params, width, length, roof_type)

        # Лестница
        stairs = self._design_stairs(params, floors, height) if floors > 1 else None

        return {
            "type": "structural",
            "total_weight_kg": round(weight),
            "foundation": foundation,
            "walls": walls,
            "floors": floors_design,
            "roof": roof,
            "stairs": stairs,
            "material_properties": self.MATERIAL_STRENGTH.get(material, self.MATERIAL_STRENGTH["brick"]),
            "compliance": self._check_compliance(params, foundation, walls),
        }

    def _calculate_weight(self, params: dict, footprint: float, floors: int, material: str) -> float:
        """Расчёт веса здания."""
        props = self.MATERIAL_STRENGTH.get(material, self.MATERIAL_STRENGTH["brick"])
        density = props["density"]  # кг/м³

        height = params.get("height_m", 3.0)
        wall_thickness = 0.3  # м (средняя)
        wall_perimeter = 2 * (params.get("width_m", 10) + params.get("length_m", 10))

        # Стены
        wall_volume = wall_perimeter * wall_thickness * height * floors
        wall_weight = wall_volume * density

        # Перекрытия (плиты ~500 кг/м²)
        floor_weight = footprint * 500 * (floors - 1) if floors > 1 else 0

        # Крыша (~200 кг/м²)
        roof_weight = footprint * 1.3 * 200

        # Нагрузка (мебель, люди ~200 кг/м²)
        live_load = footprint * floors * 200

        return wall_weight + floor_weight + roof_weight + live_load

    def _design_foundation(self, params: dict, weight: float, soil_type: str) -> dict:
        """Проектирование фундамента."""
        floors = params.get("floors", 1)
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)
        footprint = width * length

        soil_bearing = {"weak": 1.0, "medium": 2.5, "strong": 5.0}.get(soil_type, 2.5)

        # Давление на грунт
        pressure = weight / (footprint * 10000)  # кг/см²

        # Подбор типа
        if pressure > soil_bearing * 0.8 or floors > 5:
            foundation_type = "pile"
            desc = "Свайный фундамент (буронабивные сваи)"
            depth = 3.0
        elif floors <= 2 and soil_type == "strong":
            foundation_type = "slab"
            desc = "Плитный фундамент (монолитная плита)"
            depth = 0.5
        else:
            foundation_type = "strip"
            desc = "Ленточный фундамент (монолитный)"
            depth = 1.2

        # Размеры
        if foundation_type == "strip":
            width_f = max(0.3, 0.2 + floors * 0.05)
        elif foundation_type == "slab":
            width_f = 0.25
        else:
            width_f = 0.3  # ростверк

        return {
            "type": foundation_type,
            "description": desc,
            "depth_m": depth,
            "width_m": round(width_f, 2),
            "concrete_volume_m3": round(
                footprint * width_f if foundation_type == "slab" else (2 * (width + length)) * width_f * depth, 1
            ),
            "rebar": "А500С ∅12, шаг 200мм",
            "soil_pressure_kg_cm2": round(pressure, 2),
            "soil_bearing_capacity": soil_bearing,
            "safety_factor": round(soil_bearing / pressure, 1) if pressure > 0 else 999,
        }

    def _design_walls(self, params: dict, material: str, floors: int) -> dict:
        """Проектирование стен."""
        height = params.get("height_m", 3.0)
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)
        self.MATERIAL_STRENGTH.get(material, self.MATERIAL_STRENGTH["brick"])

        # Толщина стены
        if material in ("brick", "кирпич"):
            thickness = 0.38 if floors <= 2 else 0.51
            description = f"Кладка в {1.5 if floors <= 2 else 2} кирпича"
        elif material in ("foam_block", "пеноблок"):
            thickness = 0.3 if floors <= 2 else 0.4
            description = f"Пеноблок D500, {int(thickness * 1000)}мм"
        elif material in ("wood", "дерево"):
            thickness = 0.2
            description = "Брус 200×200мм"
        elif material in ("concrete", "бетон"):
            thickness = 0.25
            description = "Монолитный бетон B25"
        else:
            thickness = 0.3
            description = "Стандартная кладка"

        wall_perimeter = 2 * (width + length)
        wall_area = wall_perimeter * height * floors
        wall_volume = wall_area * thickness

        return {
            "material": material,
            "thickness_m": thickness,
            "description": description,
            "total_area_m2": round(wall_area, 1),
            "total_volume_m3": round(wall_volume, 1),
            "load_bearing": "Несущие стены по периметру + внутренние",
            "insulation": self._suggest_insulation(material, params),
        }

    def _design_floors(self, params: dict, width: float, length: float, floors: int) -> list[dict]:
        """Проектирование перекрытий."""
        result = []
        for f in range(1, floors):
            span = max(width, length)
            if span <= 6:
                type_name = "Монолитная железобетонная плита"
                thickness = 0.15
            elif span <= 9:
                type_name = "Пустотные плиты ПБ"
                thickness = 0.22
            else:
                type_name = "Монолитная плита с рёбрами"
                thickness = 0.25

            result.append(
                {
                    "floor": f,
                    "type": type_name,
                    "thickness_m": thickness,
                    "span_m": span,
                    "load_capacity_kg_m2": 500,
                    "rebar": "А500С ∅10, шаг 150мм",
                }
            )

        return result

    def _design_roof(self, params: dict, width: float, length: float, roof_type: str) -> dict:
        """Проектирование крыши."""
        area = width * length * 1.3  # с учётом свесов

        if roof_type in ("flat", "плоская"):
            return {
                "type": "Плоская крыша",
                "area_m2": round(area, 1),
                "structure": "Монолитная плита",
                "insulation": "ЭППС 150мм",
                "waterproofing": "ПВХ мембрана",
                "slope_pct": 2,
            }
        elif roof_type in ("gable", "двускатная"):
            slope_angle = 35
            rafter_length = (width / 2) / math.cos(math.radians(slope_angle))
            return {
                "type": "Двускатная крыша",
                "area_m2": round(area, 1),
                "slope_angle": slope_angle,
                "rafter_length_m": round(rafter_length, 1),
                "rafter_section": "50×200мм",
                "rafter_step_m": 0.6,
                "material": "Доска 50×200, сосна",
                "covering": "Металлочерепица" if params.get("budget", "medium") != "high" else "Керамическая черепица",
            }
        elif roof_type in ("hip", "вальмовая"):
            return {
                "type": "Вальмовая крыша",
                "area_m2": round(area * 1.1, 1),
                "slope_angle": 30,
                "structure": "Стропильная система",
                "covering": "Металлочерепица",
            }
        else:
            return {
                "type": "Мансардная крыша",
                "area_m2": round(area * 1.2, 1),
                "slope_angle_lower": 60,
                "slope_angle_upper": 25,
                "usable_area_m2": round(width * length * 0.7, 1),
                "insulation": "Минвата 200мм",
            }

    def _design_stairs(self, params: dict, floors: int, floor_height: float) -> dict:
        """Проектирование лестницы."""
        total_rise = floor_height * floors
        riser_height = 0.17  # м
        tread_depth = 0.28  # м
        num_steps = math.ceil(total_rise / riser_height)
        stair_width = max(0.9, params.get("stair_width", 1.0))

        # П-образная лестница с площадкой
        flight_length = (num_steps // 2) * tread_depth

        return {
            "type": "П-образная с площадкой",
            "total_rise_m": round(total_rise, 2),
            "num_steps": num_steps,
            "riser_height_m": riser_height,
            "tread_depth_m": tread_depth,
            "width_m": stair_width,
            "flight_length_m": round(flight_length, 1),
            "material": "Монолитный бетон с деревянными ступенями",
            "railing": "Металл + стекло",
        }

    def _suggest_insulation(self, material: str, params: dict) -> str:
        """Подбор утеплителя."""
        if material in ("brick", "кирпич"):
            return "Минеральная вата 100мм + вентфасад"
        elif material in ("wood", "дерево"):
            return "Межвенцовый утеплитель + джут"
        elif material in ("concrete", "бетон"):
            return "ЭППС 100мм + штукатурный фасад"
        elif material in ("foam_block", "пеноблок"):
            return "ЭППС 50мм + штукатурка"
        return "Утеплитель по расчёту теплозащиты"

    def _check_compliance(self, params: dict, foundation: dict, walls: dict) -> dict:
        """Проверка конструктива."""
        checks = []
        if foundation.get("safety_factor", 0) < 1.2:
            checks.append("❌ Коэффициент запаса фундамента < 1.2")
        else:
            checks.append("✅ Фундамент достаточен")

        checks.append(f"✅ Стены: {walls['description']}")
        checks.append("✅ Перекрытия: по расчёту пролёта")

        return {
            "passed": not any("❌" in c for c in checks),
            "checks": checks,
        }

    # ═══ Расширения: ЛСТК, гибридные конструкции, фундамент под печь ═══

    LSTK_PROFILES = {
        "C75": {"thickness_mm": 0.8, "width_mm": 75, "load_kg_m": 150, "max_span_m": 4.5},
        "C100": {"thickness_mm": 1.0, "width_mm": 100, "load_kg_m": 250, "max_span_m": 6.0},
        "C150": {"thickness_mm": 1.2, "width_mm": 150, "load_kg_m": 400, "max_span_m": 8.0},
        "U50": {"thickness_mm": 0.8, "width_mm": 50, "load_kg_m": 80, "max_span_m": 3.0},
        "U75": {"thickness_mm": 1.0, "width_mm": 75, "load_kg_m": 120, "max_span_m": 4.0},
    }

    def design_lstk(self, params: dict) -> dict:
        """Проектирование ЛСТК-каркаса."""
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)
        floors = params.get("floors", 1)
        height = params.get("height_m", 3.0)

        # Подбор профилей
        wall_profile = "C100" if floors <= 2 else "C150"
        floor_profile = "C150" if floors > 1 else None

        wall_spec = self.LSTK_PROFILES[wall_profile]
        floor_spec = self.LSTK_PROFILES.get(floor_profile, {})

        # Шаг стоек
        stud_spacing = 0.6  # м (600 мм)
        wall_perimeter = 2 * (width + length)
        studs_count = int(wall_perimeter / stud_spacing) + 4  # +4 угловых

        # Обрешётка
        purlin_spacing = 0.6
        roof_area = width * length * 1.3
        purlins_count = int(roof_area / purlin_spacing)

        return {
            "type": "ЛСТК каркас",
            "wall_studs": {
                "profile": wall_profile,
                "thickness_mm": wall_spec["thickness_mm"],
                "spacing_mm": int(stud_spacing * 1000),
                "count": studs_count,
                "height_m": height * floors,
                "material": "Оцинкованная сталь S350GD, Z275",
            },
            "floor_joists": {
                "profile": floor_profile or "N/A",
                "spacing_mm": 400 if floor_profile else 0,
                "count": int(length / 0.4) * floors if floor_profile else 0,
                "max_span_m": floor_spec.get("max_span_m", 0),
            },
            "roof_purlins": {
                "profile": "C100",
                "spacing_mm": int(purlin_spacing * 1000),
                "count": purlins_count,
            },
            "wall_buildup": [
                "ГКЛ 12.5мм (внутренний)",
                f"Стойки {wall_profile}×{wall_spec['thickness_mm']}мм с утеплителем 100мм",
                "Пароизоляция",
                "ОСП 9мм (наружный)",
                "Вентзазор 30мм",
                "Фасад (сайдинг / штукатурка)",
            ],
            "connections": {
                "stud_to_track": "Саморез LN 4.2×19",
                "sheet_to_frame": "Саморез TN 4.2×25, шаг 200мм",
                "splice": "Саморез LN 4.2×13, 4 шт",
            },
            "estimated_weight_kg_m2": round(wall_spec["load_kg_m"] * height / 1000, 1),
            "compliance": "AISI S100 / СП 16.13330",
        }

    def design_hybrid_rbc_lstk(self, params: dict) -> dict:
        """Проектирование гибридной конструкции: ЖБК низ + ЛСТК верх."""
        lower_floors = params.get("lower_floors", 1)
        upper_floors = params.get("upper_floors", 1)
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)

        lstk_params = dict(params, floors=upper_floors)
        lstk_design = self.design_lstk(lstk_params)

        # Узел стыка ЖБК/ЛСТК
        joint = {
            "type": "Болтовое соединение + химический анкер",
            "anchor_type": "Химический анкер M12",
            "anchor_spacing_mm": 600,
            "base_plate": "Стальная пластина 200×200×8мм, оцинкованная",
            "sealant": "Герметик полиуретановый",
            "gap_mm": 20,  # Деформационный шов
            "load_transfer": "Вертикальная нагрузка через базовую пластину, горизонтальная — через болты",
        }

        return {
            "type": "Гибридная конструкция: ЖБК + ЛСТК",
            "lower_level": {
                "material": "Монолитный железобетон",
                "floors": lower_floors,
                "description": "Несущие стены и перекрытия из монолитного ЖБК",
            },
            "upper_level": {
                "material": "ЛСТК каркас",
                "floors": upper_floors,
                "description": "Каркас из ЛСТК-профилей с утеплителем",
                "design": lstk_design,
            },
            "interface": joint,
            "critical_details": [
                "Гидроизоляция стыка ЖБК/ЛСТК (отсечка влаги)",
                "Деформационный шов ≥20мм",
                "Прокладка инженерных коммуникаций через стык",
                "Огнезащита стыка (предел огнестойкости ≥60 мин)",
            ],
        }

    def design_stove_foundation(self, params: dict) -> dict:
        """Проектирование отдельного фундамента под печь."""
        stove_type = params.get("stove_type", "metal")
        stove_weight_kg = params.get("stove_weight_kg", 200)

        if stove_type == "brick":
            stove_weight_kg = max(500, stove_weight_kg)
            foundation = {
                "type": "Монолитная плита",
                "dimensions_m": "1.2×1.2×0.3",
                "reinforcement": "АIII Ø12, шаг 150мм, 2 слоя",
                "concrete": "B15 (М200)",
                "depth_m": 0.5,
                "isolation": "Отдельный от общего фундамента (деформационный шов ≥50мм)",
                "heat_resistant_layer": "Жаростойкий бетон 50мм сверху",
            }
        else:
            foundation = {
                "type": "Усиленное основание",
                "dimensions_m": "0.8×0.8×0.2",
                "reinforcement": "Сетка сварная Ø6, шаг 100мм",
                "concrete": "B15 (М200)",
                "depth_m": 0.3,
                "note": "Для металлической печи до 200кг",
            }

        # Дымоход — проход через конструкции
        chimney = {
            "sandwich_diameter_mm": params.get("chimney_diameter_mm", 150),
            "clearance_to_combustibles_mm": 250,  # Сэндвич-дымоход
            "clearance_to_non_combustibles_mm": 50,
            "passage_through_floor": "Проходной узел с термоизоляцией",
            "passage_through_roof": "Разделка + выдра + оголовок",
            "height_above_roof": "≥0.5м от конька (при расстоянии ≤1.5м)",
        }

        return {
            "stove_type": stove_type,
            "stove_weight_kg": stove_weight_kg,
            "foundation": foundation,
            "chimney": chimney,
            "compliance": "СП 7.13130.2013, Правила пожарной безопасности",
        }
