"""
shared/compliance.py — Расширенная проверка соответствия нормативам (v2.0)

Нормы:
  СП 54.13330.2016  — Жилые здания
  СП 1.13130.2020   — Эвакуационные пути
  СП 2.13130.2020   — Противопожарная защита
  СП 50.13330.2012  — Теплозащита
  СП 59.13330.2016  — Доступность МГН
  СП 63.13330.2018  — ЖБ конструкции
  СП 16.13330.2017  — Стальные конструкции
  СП 22.13330.2016  — Основания
  СП 24.13330.2011  — Свайные фундаменты
  СП 7.13130.2013   — HVAC
  СП 30.13330.2020  — Водопровод/канализация
  СП 76.13330.2016  — Электрооборудование
  ГОСТ 30247.0      — Огнестойкость
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("archai.compliance")


@dataclass
class ComplianceIssue:
    code: str
    severity: str  # "error" | "warning" | "info"
    message: str
    fix: str = ""
    standard: str = ""
    category: str = ""


@dataclass
class ComplianceResult:
    passed: bool = True
    issues: list[ComplianceIssue] = field(default_factory=list)
    warnings: list[ComplianceIssue] = field(default_factory=list)
    score: float = 1.0
    checks_run: list[str] = field(default_factory=list)

    def add_error(self, code, message, fix="", standard="", category=""):
        self.issues.append(
            ComplianceIssue(code=code, severity="error", message=message, fix=fix, standard=standard, category=category)
        )
        self.passed = False

    def add_warning(self, code, message, fix="", standard="", category=""):
        self.warnings.append(
            ComplianceIssue(
                code=code, severity="warning", message=message, fix=fix, standard=standard, category=category
            )
        )

    def to_dict(self):
        return {
            "passed": self.passed,
            "issues": [
                {
                    "code": i.code,
                    "severity": i.severity,
                    "message": i.message,
                    "fix": i.fix,
                    "standard": i.standard,
                    "category": i.category,
                }
                for i in self.issues
            ],
            "warnings": [
                {
                    "code": w.code,
                    "severity": w.severity,
                    "message": w.message,
                    "fix": w.fix,
                    "standard": w.standard,
                    "category": w.category,
                }
                for w in self.warnings
            ],
            "score": self.score,
            "checks_run": self.checks_run,
        }


class ComplianceChecker:
    """Полная проверка соответствия всем нормативам."""

    def check_building(self, params: dict, building_params: dict) -> ComplianceResult:
        """Запустить все проверки."""
        result = ComplianceResult()

        self._check_sp54_residential(params, building_params, result)
        self._check_sp113130_fire(params, building_params, result)
        self._check_sp213130_fire_protection(params, building_params, result)
        self._check_room_sizes(params, building_params, result)
        self._check_natural_light(params, building_params, result)
        self._check_accessibility(params, building_params, result)
        self._check_energy_efficiency(params, building_params, result)
        self._check_structural_concrete(params, building_params, result)
        self._check_structural_steel(params, building_params, result)
        self._check_foundation(params, building_params, result)
        self._check_mep_hvac(params, building_params, result)
        self._check_mep_plumbing(params, building_params, result)
        self._check_mep_electrical(params, building_params, result)
        self._check_roof(params, building_params, result)

        error_count = len(result.issues)
        warning_count = len(result.warnings)
        penalty = error_count * 0.1 + warning_count * 0.03
        result.score = max(0.0, 1.0 - penalty)
        result.passed = error_count == 0

        return result

    # ── СП 54.13330 — Жилые здания ───────────────────────────────
    def _check_sp54_residential(self, params, bp, result):
        result.checks_run.append("SP_54")
        floors = bp.get("floors", 2)
        fh = bp.get("fH", 2.8)
        rooms = bp.get("rooms", [])

        if fh < 2.5:
            result.add_error(
                "SP_54_3.7", f"Высота потолка {fh}м < 2.5м", "Увеличить до ≥2.5м", "СП 54.13330.2016", "layout"
            )
        elif fh < 2.7:
            result.add_warning(
                "SP_54_3.7",
                f"Высота потолка {fh}м < 2.7м (рекомендуется)",
                "Увеличить до ≥2.7м",
                "СП 54.13330.2016",
                "layout",
            )

        for room in rooms:
            tag = room.get("tag", "")
            area = room.get("a", 0)
            name = room.get("n", "")
            if tag == "l" and area < 12:
                result.add_error(
                    "SP_54_3.8", f"Гостиная '{name}' = {area}м² < 12м²", "Увеличить ≥12м²", "СП 54.13330.2016", "layout"
                )
            elif tag == "k" and area < 8:
                result.add_error(
                    "SP_54_3.8", f"Кухня '{name}' = {area}м² < 8м²", "Увеличить ≥8м²", "СП 54.13330.2016", "layout"
                )
            elif tag == "s" and area < 9:
                result.add_error(
                    "SP_54_3.8", f"Спальня '{name}' = {area}м² < 9м²", "Увеличить ≥9м²", "СП 54.13330.2016", "layout"
                )

        if fh * floors > 75:
            result.add_error(
                "SP_54_3.10",
                f"Высота здания {fh * floors}м > 75м — высотное здание",
                "Применить доп. требования",
                "СП 54.13330.2016",
                "structural",
            )

    # ── СП 1.13130 — Эвакуация ──────────────────────────────────
    def _check_sp113130_fire(self, params, bp, result):
        result.checks_run.append("SP_1_13130")
        w, L = bp.get("W", 10), bp.get("L", 12)
        floors = bp.get("floors", 2)
        rooms = bp.get("rooms", [])

        if max(w, L) > 40:
            result.add_warning(
                "SP_1_13130_4.2",
                f"Расстояние до выхода {max(w, L)}м > 40м",
                "Добавить эвакуационный выход",
                "СП 1.13130.2020",
                "fire",
            )

        for r in rooms:
            if r.get("tag") == "h" and r.get("w", 0) < 1.2:
                result.add_error(
                    "SP_1_13130_4.3",
                    f"Коридор '{r.get('n', '')}' шириной {r.get('w', 0)}м < 1.2м",
                    "Увеличить ≥1.2м",
                    "СП 1.13130.2020",
                    "fire",
                )

        if floors > 1:
            min_sw = 0.9 if params.get("building_type") in ("house", "cottage") else 1.2
            result.add_warning(
                "SP_1_13130_5.2", f"Лестничный марш ≥{min_sw}м", "Проверить ширину лестницы", "СП 1.13130.2020", "fire"
            )

    # ── СП 2.13130 — Противопожарная защита ──────────────────────
    def _check_sp213130_fire_protection(self, params, bp, result):
        result.checks_run.append("SP_2_13130")
        floors = bp.get("floors", 2)
        bt = params.get("building_type", "house")
        material = bp.get("mat", params.get("material", "brick"))

        # Класс огнестойкости по типу здания
        required_rei = {
            "house": "R45",
            "office": "R60",
            "hotel": "R60",
            "commercial": "R60",
            "school": "R60",
            "hospital": "R90",
        }
        required = required_rei.get(bt, "R45")

        # Определение фактического класса
        if material in ("concrete", "brick"):
            actual = "R120" if floors > 3 else "R60"
        elif material == "steel":
            actual = "R30"
        elif material == "wood":
            actual = "R15"
        else:
            actual = "R45"

        rei_values = {"R15": 15, "R30": 30, "R45": 45, "R60": 60, "R90": 90, "R120": 120, "R150": 150, "R180": 180}
        if rei_values.get(actual, 0) < rei_values.get(required, 0):
            result.add_error(
                "SP_2_13130",
                f"Огнестойкость {actual} < требуемой {required} для '{bt}'",
                f"Усилить конструкцию до {required}",
                "СП 2.13130.2020",
                "fire",
            )

        # Площадь пожарного отсека
        area = bp.get("W", 10) * bp.get("L", 12) * floors
        max_compartment = {"house": 1500, "office": 2500, "hotel": 2500, "commercial": 2000}
        limit = max_compartment.get(bt, 2500)
        if area > limit:
            result.add_warning(
                "SP_2_13130_5.1",
                f"Площадь {area}м² > лимита пожарного отсека {limit}м²",
                "Разделить на пожарные отсеки",
                "СП 2.13130.2020",
                "fire",
            )

    # ── Проверка размеров помещений ──────────────────────────────
    def _check_room_sizes(self, params, bp, result):
        result.checks_run.append("room_sizes")
        for r in bp.get("rooms", []):
            if r.get("w", 0) < 2.0 and r.get("d", 0) < 2.0:
                result.add_warning(
                    "ROOM_SIZE",
                    f"Комната '{r.get('n', '')}' слишком маленькая ({r.get('w', 0)}×{r.get('d', 0)}м)",
                    "Увеличить ≥2.0м",
                    category="layout",
                )

    # ── Естественное освещение ───────────────────────────────────
    def _check_natural_light(self, params, bp, result):
        result.checks_run.append("natural_light")
        for r in bp.get("rooms", []):
            if r.get("tag") in ("l", "s") and r.get("a", 0) > 20:
                needed = r["a"] / 8
                result.add_warning(
                    "NATURAL_LIGHT",
                    f"'{r.get('n', '')}' ({r['a']}м²) — остекление ≥{needed:.1f}м²",
                    "Добавить окна",
                    "СП 54.13330.2016 п.6.2",
                    "layout",
                )

    # ── Доступность МГН (СП 59) ─────────────────────────────────
    def _check_accessibility(self, params, bp, result):
        result.checks_run.append("accessibility")
        floors = bp.get("floors", 2)
        bt = params.get("building_type", "house")

        if bt in ("office", "hotel", "commercial") and floors > 1:
            if not params.get("has_elevator"):
                result.add_warning(
                    "ACCESS_ELEVATOR",
                    f"'{bt}' с {floors} этажами — нужен лифт",
                    "Добавить пассажирский лифт",
                    "СП 59.13330.2016",
                    "accessibility",
                )

        if bt in ("office", "hotel", "commercial", "public"):
            result.add_warning(
                "ACCESS_RAMP",
                "Требуется пандус на входе (уклон ≤ 1:12)",
                "Спроектировать пандус",
                "СП 59.13330.2016",
                "accessibility",
            )
            result.add_warning(
                "ACCESS_DOOR",
                "Ширина дверных проёмов ≥ 0.9м",
                "Проверить все двери",
                "СП 59.13330.2016",
                "accessibility",
            )

        if bt in ("office", "hotel", "commercial"):
            result.add_warning(
                "ACCESS_BATHROOM",
                "Требуется доступный санузел (2.2×2.2м мин.)",
                "Выделить доступный санузел",
                "СП 59.13330.2016",
                "accessibility",
            )
            result.add_warning(
                "ACCESS_TACTILE",
                "Тактильная навигация и визуальные оповещатели",
                "Добавить тактильные таблички и световые оповещатели",
                "СП 59.13330.2016",
                "accessibility",
            )

    # ── Теплозащита (СП 50) ─────────────────────────────────────
    def _check_energy_efficiency(self, params, bp, result):
        result.checks_run.append("energy")
        material = bp.get("mat", params.get("material", "plaster"))
        floors = bp.get("floors", 2)
        fh = bp.get("fH", 2.8)
        wt = bp.get("wall_thickness", 0.3)

        # U-value check (СП 50.13330)
        if material == "brick" and wt < 0.4:
            result.add_warning(
                "ENERGY_WALL",
                f"Кирпичная стена {wt}м — нужно утепление",
                "Добавить 100-150мм утеплителя",
                "СП 50.13330.2012",
                "energy",
            )

        w, L = bp.get("W", 10), bp.get("L", 12)
        wall_area = 2 * (w + L) * fh * floors
        result.add_warning(
            "ENERGY_WINDOW",
            f"Площадь стен ≈{wall_area:.0f}м² — окна ≤40% ({wall_area * 0.4:.0f}м²)",
            "Проверить остекление",
            "СП 50.13330.2012",
            "energy",
        )

        # Проверка конденсации (упрощённая)
        if material == "glass" or (material in ("стекло",) and wt < 0.05):
            result.add_warning(
                "ENERGY_CONDENSATION",
                "Стеклянный фасад — риск конденсации",
                "Применить двухкамерные стеклопакеты",
                "СП 50.13330.2012",
                "energy",
            )

    # ── СП 63 — ЖБ конструкции ──────────────────────────────────
    def _check_structural_concrete(self, params, bp, result):
        result.checks_run.append("SP_63")
        material = params.get("material", "brick")

        if material not in ("concrete", "reinforced_concrete", "железобетон", "бетон"):
            return

        concrete_class = params.get("concrete_class", "B25")
        floors = bp.get("floors", 2)

        # Минимальная толщина защитного слоя (СП 63 п.10.2)
        cover_table = {"XC1": 20, "XC2": 25, "XC3": 30, "XC4": 35, "XD1": 35}
        exposure = params.get("exposure_class", "XC1")
        min_cover = cover_table.get(exposure, 25)

        result.add_warning(
            "SP_63_COVER",
            f"Защитный слой бетона ≥{min_cover}мм (класс условий {exposure})",
            f"Обеспечить защитный слой ≥{min_cover}мм",
            "СП 63.13330.2018",
            "structural",
        )

        # Минимальный % армирования (СП 63 п.10.3.6)
        result.add_warning(
            "SP_63_REBAR_MIN",
            "Минимальное армирование: 0.1% для изгибаемых, 0.05% для сжатых",
            "Проверить процент армирования",
            "СП 63.13330.2018",
            "structural",
        )

        # Максимальный % армирования
        result.add_warning(
            "SP_63_REBAR_MAX",
            "Максимальный % армирования: 5% для сжатых, 4% для изгибаемых",
            "Не превышать максимум",
            "СП 63.13330.2018",
            "structural",
        )

    # ── СП 16 — Стальные конструкции ─────────────────────────────
    def _check_structural_steel(self, params, bp, result):
        result.checks_run.append("SP_16")
        material = params.get("material", "brick")

        if material not in ("steel", "сталь"):
            return

        steel_grade = params.get("steel_grade", "C345")
        floors = bp.get("floors", 2)
        L = bp.get("L", 12)

        # Предел прогиба (СП 16 табл. 18)
        result.add_warning(
            "SP_16_DEFLECTION",
            f"Предел прогиба: L/250 = {L / 250 * 1000:.0f}мм",
            "Проверить прогиб балок",
            "СП 16.13330.2017",
            "structural",
        )

        # Защита от коррозии
        result.add_warning(
            "SP_16_CORROSION",
            "Стальные конструкции требуют антикоррозийной защиты",
            "Нанести грунтовку + 2 слоя эмали",
            "СП 16.13330.2017",
            "structural",
        )

        # Огнезащита
        if floors > 1:
            result.add_warning(
                "SP_16_FIRE_PROTECT",
                "Стальные конструкции в многоэтажках — огнезащита обязательна",
                "Применить огнезащитные покрытия",
                "СП 2.13130.2020",
                "fire",
            )

    # ── СП 22/24 — Основания ─────────────────────────────────────
    def _check_foundation(self, params, bp, result):
        result.checks_run.append("SP_22")
        ft = params.get("foundation_type", "strip")
        soil = params.get("soil_type", "III")
        floors = bp.get("floors", 2)

        # Минимальная глубина заложения (СП 22 п.12.3)
        min_depth_map = {"I": 0.5, "II": 0.5, "III": 0.7, "IV": 1.0, "V": 1.2}
        min_depth = min_depth_map.get(soil, 0.7)
        actual_depth = params.get("foundation_depth_m", min_depth)

        if actual_depth < min_depth:
            result.add_error(
                "SP_22_DEPTH",
                f"Глубина заложения {actual_depth}м < {min_depth}м для грунта '{soil}'",
                f"Увеличить глубину до ≥{min_depth}м",
                "СП 22.13330.2016",
                "structural",
            )

        if ft == "pile":
            pile_d = params.get("pile_diameter_m", 0.3)
            pile_spacing = params.get("pile_spacing_m", 0.9)
            min_spacing = 3 * pile_d
            if pile_spacing < min_spacing:
                result.add_error(
                    "SP_24_SPACING",
                    f"Расстояние между сваями {pile_spacing}м < {min_spacing}м",
                    f"Увеличить расстояние до ≥{min_spacing}м",
                    "СП 24.13330.2011",
                    "structural",
                )

    # ── СП 7 — HVAC ─────────────────────────────────────────────
    def _check_mep_hvac(self, params, bp, result):
        result.checks_run.append("SP_7_HVAC")
        bt = params.get("building_type", "house")

        if bt in ("office", "hotel", "commercial"):
            result.add_warning(
                "SP_7_VENT",
                "Требуется приточно-вытяжная вентиляция (60м³/ч на человека)",
                "Спроектировать систему вентиляции",
                "СП 7.13130.2013",
                "mep",
            )

        if bt == "house":
            result.add_warning(
                "SP_7_VENT_RESID",
                "Естественная вентиляция: 3м³/ч на 1м² жилой площади",
                "Обеспечить приточные клапаны",
                "СП 7.13130.2013",
                "mep",
            )

    # ── СП 30 — Водоснабжение ────────────────────────────────────
    def _check_mep_plumbing(self, params, bp, result):
        result.checks_run.append("SP_30")
        rooms = bp.get("rooms", [])
        has_bathroom = any(r.get("tag") in ("bath", "bathroom") for r in rooms)
        has_kitchen = any(r.get("tag") == "k" for r in rooms)

        if has_bathroom:
            result.add_warning(
                "SP_30_HOT_WATER", "Горячее водоснабжение: 60-75°C", "Обеспечить ГВС", "СП 30.13330.2020", "mep"
            )
        if has_kitchen:
            result.add_warning(
                "SP_30_COLD_WATER", "Холодное водоснабжение: ≤75°C", "Обеспечить ХВС", "СП 30.13330.2020", "mep"
            )

    # ── СП 76 — Электрика ────────────────────────────────────────
    def _check_mep_electrical(self, params, bp, result):
        result.checks_run.append("SP_76")
        bt = params.get("building_type", "house")

        load_map = {"house": "5-7 кВт на дом", "office": "50-80 Вт/м²", "commercial": "80-120 Вт/м²"}
        result.add_warning(
            "SP_76_LOAD",
            f"Удельная электрическая нагрузка: {load_map.get(bt, '50-80 Вт/м²')}",
            "Рассчитать электрическую нагрузку",
            "СП 76.13330.2016",
            "mep",
        )

    # ── СП 17 — Кровли ──────────────────────────────────────────
    def _check_roof(self, params, bp, result):
        result.checks_run.append("SP_17")
        roof = params.get("roof_type", "gabled")

        if roof == "flat":
            result.add_warning(
                "SP_17_FLAT",
                "Плоская кровля — требуется усиленная гидроизоляция и дренаж",
                "Применить ПВХ/ТПО мембрану + организовать внутренний водосток",
                "СП 17.13330.2017",
                "roof",
            )
        elif roof in ("gabled", "hip"):
            result.add_warning(
                "SP_17_SLOPED",
                f"Скатная кровля ({roof}) — уклон ≥ 15%",
                "Проверить уклон и водосточную систему",
                "СП 17.13330.2017",
                "roof",
            )


def quick_compliance_check(params: dict, building_params: dict) -> dict:
    """Быстрая проверка для оркестратора."""
    checker = ComplianceChecker()
    result = checker.check_building(params, building_params)
    return result.to_dict()
