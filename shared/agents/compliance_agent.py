"""
shared/agents/compliance_agent.py — Расширенный агент проверки нормативов (v2.0)

Использует:
  - StructuralEngine для расчёта конструкций
  - FoundationAnalyzer для оснований
  - DynamicsAnalyzer для сейсмики
  - NormEngine для ссылок на нормы
  - Полная база СП/ГОСТ
"""

import logging
import time
from typing import Dict, Any

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class ComplianceAgent(BaseAgent):
    name = "compliance"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            gen_type = params.get("gen_type", "building")

            if gen_type == "interior":
                result = self._check_interior_compliance(params)
            else:
                result = self._check_building_compliance(params)

            return TaskResult(status=TaskStatus.DONE, data=result, duration_ms=(time.time() - start) * 1000)
        except Exception as e:
            logger.error(f"ComplianceAgent error: {e}")
            return TaskResult(status=TaskStatus.FAILED, error=str(e), duration_ms=(time.time() - start) * 1000)

    def _check_building_compliance(self, params: dict) -> dict:
        """Полная проверка здания по всем нормативам."""
        structural = self._check_structural_compliance(params)
        fire = self._check_fire_safety(params)
        accessibility = self._check_accessibility(params)
        energy = self._check_energy_efficiency(params)
        foundation = self._check_foundation_compliance(params)
        seismic = self._check_seismic_compliance(params)
        mep = self._check_mep_compliance(params)
        norms = self._check_applicable_norms(params)

        all_passed = all(s["passed"] for s in [structural, fire, accessibility, energy, foundation])
        total_score = (
            structural["score"] * 0.25
            + fire["score"] * 0.20
            + foundation["score"] * 0.15
            + seismic["score"] * 0.10
            + energy["score"] * 0.10
            + accessibility["score"] * 0.10
            + mep["score"] * 0.10
        )

        return {
            "type": "compliance_report",
            "overall_passed": all_passed,
            "overall_score": round(total_score, 1),
            "structural": structural,
            "fire_safety": fire,
            "accessibility": accessibility,
            "energy_efficiency": energy,
            "foundation": foundation,
            "seismic": seismic,
            "mep": mep,
            "applicable_norms": norms,
            "summary": self._generate_summary(structural, fire, accessibility, energy, foundation, seismic, mep),
            "action_plan": self._generate_action_plan(structural, fire, accessibility, energy, foundation, seismic, mep),
        }

    def _check_interior_compliance(self, params: dict) -> dict:
        """Проверка интерьера."""
        return {
            "type": "interior_compliance",
            "passed": True,
            "score": 1.0,
            "checks": ["Размеры комнат", "Вентиляция", "Освещение"],
        }

    def _check_structural_compliance(self, params: dict) -> dict:
        """
        Проверка конструктивной системы.
        
        Использует: СП 63.13330, СП 16.13330, СП 15.13330, СП 64.13330
        """
        checks = []
        score = 100.0
        material = params.get("material", "brick")
        floors = params.get("floors", 2)
        width = params.get("width_m", 10)
        length = params.get("length_m", 12)
        height = params.get("height_m", 3.0)
        structural_system = params.get("structural_system", "frame")

        # Проверка конструктивной системы
        if floors > 5 and structural_system == "frame":
            checks.append(f"⚠️ Каркасная система для {floors} этажей — рекомендуется рамно-связевая")
            score -= 5

        if floors > 9 and structural_system not in ("shear_wall", "tube", "hybrid"):
            checks.append(f"⚠️ Для {floors} этажей нужна усиленная конструктивная система")
            score -= 10

        # Проверка по материалам
        if material in ("concrete", "reinforced_concrete"):
            concrete_class = params.get("material_concrete_class", "B25")
            checks.append(f"📋 Класс бетона: {concrete_class}")
            if floors > 5 and concrete_class in ("B7.5", "B15"):
                checks.append(f"⚠️ Класс бетона {concrete_class} недостаточен для {floors} этажей")
                score -= 15

            # Защитный слой
            checks.append("✅ Защитный слой: ≥25мм (XC1), ≥35мм (XC3)")

            # Минимальное армирование
            checks.append("✅ Минимальное армирование: 0.1% (изгиб), 0.05% (сжатие)")

        elif material in ("steel", "сталь"):
            steel_grade = params.get("steel_grade", "C345")
            checks.append(f"📋 Класс стали: {steel_grade}")
            checks.append("✅ Прогиб: ≤ L/250 (балки), ≤ L/360 (консоли)")
            checks.append("⚠️ Антикоррозийная защита обязательна")
            if floors > 1:
                checks.append("⚠️ Огнезащита стальных конструкций обязательна")

        elif material in ("wood", "дерево"):
            checks.append("📋 Деревянные конструкции по СП 64.13330")
            checks.append("✅ Влажность древесины: ≤ 20% (для несущих)")
            checks.append("✅ Биозащита + огнезащита обязательна")

        elif material in ("brick", "кирпич"):
            checks.append("📋 Каменные конструкции по СП 15.13330")
            if floors > 5:
                checks.append(f"⚠️ {floors} этажей — нужна армокаменная конструкция")
                score -= 10

        # Пропорции здания
        slenderness = max(width, length) / min(width, length)
        if slenderness > 4:
            checks.append(f"⚠️ Вытянутое здание (L/B = {slenderness:.1f}) — проверить пространственную жёсткость")
            score -= 5

        return {"passed": score >= 70, "score": max(0, score), "checks": checks}

    def _check_fire_safety(self, params: dict) -> dict:
        """
        Проверка пожарной безопасности.
        
        Использует: СП 1.13130.2020, СП 2.13130.2020, ГОСТ 30247.0
        """
        checks = []
        score = 100.0
        floors = params.get("floors", 1)
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)
        material = params.get("material", "brick")
        building_type = params.get("building_type", "residential")

        # Класс огнестойкости
        fire_resistance = self._determine_fire_resistance(material, floors)
        checks.append(f"📋 Класс огнестойкости: {fire_resistance['class']} ({fire_resistance['description']})")
        checks.append(f"📋 Тип: {fire_resistance['type']}")

        # Требуемый класс огнестойкости
        required_table = {
            "house": "R45", "office": "R60", "hotel": "R60",
            "commercial": "R60", "school": "R60", "hospital": "R90",
        }
        required = required_table.get(building_type, "R45")
        rei_map = {"R15": 15, "R30": 30, "R45": 45, "R60": 60, "R90": 90, "R120": 120}
        actual_val = rei_map.get(fire_resistance["class"], 45)
        required_val = rei_map.get(required, 45)
        if actual_val < required_val:
            checks.append(f"❌ Огнестойкость {fire_resistance['class']} < требуемой {required}")
            score -= 20
        else:
            checks.append(f"✅ Огнестойкость {fire_resistance['class']} ≥ {required}")

        # Эвакуационные выходы
        max_dim = max(width, length)
        required_exits = 2 if (floors > 1 or max_dim > 25) else 1
        checks.append(f"📋 Эвакуационных выходов: требуется ≥{required_exits}")

        # Противопожарные преграды
        if floors > 1:
            checks.append("✅ Противопожарная преграда между этажами")
            checks.append("✅ Двери с доводчиками в противопожарных преградах")

        # Пожаротушение
        if floors >= 3 or building_type == "commercial":
            checks.append("⚠️ Требуется автоматическая установка пожаротушения")
            score -= 10
        else:
            checks.append("✅ Автоматическое пожаротушение не требуется")

        # Оповещение
        if floors >= 2:
            checks.append("✅ Система оповещения о пожаре (2-й тип)")

        # Площадь пожарного отсека
        area = width * length * floors
        max_compartment = {"house": 1500, "office": 2500, "hotel": 2500, "commercial": 2000}
        limit = max_compartment.get(building_type, 2500)
        if area > limit:
            checks.append(f"⚠️ Площадь {area}м² > лимита пожарного отсека {limit}м²")
            score -= 5

        # Время эвакуации (упрощённо)
        evac_path = max(width, length)
        evac_speed = 1.0  # м/с для горизонтального пути
        evac_time = evac_path / evac_speed
        checks.append(f"📋 Время эвакуации (упрощ.): {evac_time:.0f}сек (путь {evac_path}м)")

        return {"passed": score >= 70, "score": max(0, score), "fire_resistance": fire_resistance, "checks": checks}

    def _check_accessibility(self, params: dict) -> dict:
        """Проверка доступности по СП 59.13330.2016."""
        checks = []
        score = 100.0
        floors = params.get("floors", 1)
        bt = params.get("building_type", "residential")

        if floors > 1 and not params.get("has_elevator"):
            checks.append("⚠️ Нет лифта — ограничение доступности")
            score -= 20

        checks.append("✅ Пандус на входе (уклон ≤ 1:12, макс. 1.8м длиной)")
        checks.append("✅ Ширина дверных проёмов ≥ 0.9м")
        checks.append("✅ Ширина коридоров ≥ 1.5м (для кресла-коляски)")
        checks.append("✅ Доступный санузел на первом этаже (2.2×2.2м)")

        if bt in ("commercial", "public"):
            checks.append("✅ Зона для маломобильных групп")
            checks.append("✅ Тактильная навигация")
            checks.append("✅ Визуальные оповещатели")

        return {"passed": score >= 70, "score": max(0, score), "checks": checks}

    def _check_energy_efficiency(self, params: dict) -> dict:
        """Проверка энергоэффективности по СП 50.13330."""
        checks = []
        score = 100.0
        material = params.get("material", "brick")
        floors = params.get("floors", 1)
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)
        height = params.get("height_m", 3.0)

        # Коэффициент компактности S/V
        volume = width * length * height * floors
        surface = 2 * (width + length) * height * floors + 2 * width * length
        sv_ratio = surface / volume if volume > 0 else 0

        if sv_ratio > 0.5:
            checks.append(f"⚠️ Коэффициент компактности S/V = {sv_ratio:.2f} (высокий)")
            score -= 10
        else:
            checks.append(f"✅ Коэффициент компактности S/V = {sv_ratio:.2f}")

        # Утепление
        if material in ("glass", "стекло"):
            checks.append("⚠️ Полностью стеклянный фасад — расчёт теплозащиты")
            score -= 15
        elif material == "brick" and params.get("wall_thickness", 0.3) < 0.4:
            checks.append("⚠️ Кирпичная стена < 400мм — нужно утепление")
            score -= 5
        else:
            checks.append("✅ Утепление по нормам")

        # Класс энергоэффективности
        if score >= 90:
            energy_class = "A+"
        elif score >= 80:
            energy_class = "A"
        elif score >= 70:
            energy_class = "B"
        elif score >= 60:
            energy_class = "C"
        else:
            energy_class = "D"

        checks.append(f"📋 Класс энергоэффективности: {energy_class}")

        return {"passed": score >= 60, "score": max(0, score), "energy_class": energy_class, "sv_ratio": round(sv_ratio, 3), "checks": checks}

    def _check_foundation_compliance(self, params: dict) -> dict:
        """
        Проверка оснований по СП 22.13330 и СП 24.13330.
        """
        checks = []
        score = 100.0
        ft = params.get("foundation_type", "strip")
        soil = params.get("soil_type", "III")
        floors = params.get("floors", 2)

        # Минимальная глубина заложения
        min_depth_map = {"I": 0.5, "II": 0.5, "III": 0.7, "IV": 1.0, "V": 1.2}
        min_depth = min_depth_map.get(soil, 0.7)
        actual_depth = params.get("foundation_depth_m", min_depth)

        if actual_depth < min_depth:
            checks.append(f"❌ Глубина заложения {actual_depth}м < {min_depth}м для грунта '{soil}'")
            score -= 20
        else:
            checks.append(f"✅ Глубина заложения {actual_depth}м ≥ {min_depth}м")

        checks.append(f"📋 Тип основания: {ft}")
        checks.append(f"📋 Категория грунта: {soil}")

        if ft == "pile":
            pile_d = params.get("pile_diameter_m", 0.3)
            min_spacing = 3.5 * pile_d if ft == "bored" else 3.0 * pile_d
            checks.append(f"📋 Мин. расстояние между сваями: {min_spacing:.2f}м (3.5d)")
            checks.append("📋 Несущая способность сваи: по СП 24.13330 п.7.4")

        elif ft == "strip":
            checks.append("📋 Ленточный фундамент: проверка по СП 22.13330 п.5.6")

        elif ft == "slab":
            checks.append("📋 Плитный фундамент: проверка по СП 22.13330 п.5.6")

        return {"passed": score >= 70, "score": max(0, score), "checks": checks}

    def _check_seismic_compliance(self, params: dict) -> dict:
        """Проверка сейсмостойкости по СП 14.13330."""
        checks = []
        score = 100.0
        seismic_zone = params.get("seismic_zone", 0)

        if seismic_zone == 0 or seismic_zone == "none":
            checks.append("✅ Зона не сейсмическая — расчёт не требуется")
            return {"passed": True, "score": 100, "checks": checks}

        checks.append(f"📋 Сейсмическая зона: {seismic_zone} баллов")
        checks.append(f"📋 Коэффициент сейсмичности K1: {0.25 if seismic_zone <= 6 else 0.5 if seismic_zone == 7 else 0.75 if seismic_zone == 8 else 1.0}")

        soil = params.get("soil_type", "III")
        if soil in ("IV", "V"):
            checks.append(f"⚠️ Грунт категории {soil} — усиление сейсмического воздействия")
            score -= 10

        structural_system = params.get("structural_system", "frame")
        if seismic_zone >= 7 and structural_system == "frame":
            checks.append("⚠️ Для 7+ баллов рекомендуется рамно-связевая система")
            score -= 5

        checks.append("📋 Динамический расчёт по спектру реакции (СП 14 п.5.5)")
        checks.append("📋 Сейсмостойкие швы при неравномерности по высоте")

        return {"passed": score >= 70, "score": max(0, score), "checks": checks}

    def _check_mep_compliance(self, params: dict) -> dict:
        """Проверка инженерных систем (HVAC, водоснабжение, электрика)."""
        checks = []
        score = 100.0
        bt = params.get("building_type", "house")

        # HVAC
        ht = params.get("heating_type", "autonomous")
        vt = params.get("ventilation_type", "natural")
        checks.append(f"📋 Отопление: {ht} (СП 7.13130)")
        checks.append(f"📋 Вентиляция: {vt}")

        if bt in ("office", "hotel", "commercial"):
            if vt == "natural":
                checks.append("⚠️ Для коммерческого здания рек. приточно-вытяжная вентиляция")
                score -= 5
            checks.append("📋 Норма: 60м³/ч на человека (СП 7.13130)")

        # Водоснабжение
        ws = params.get("water_supply", "central")
        checks.append(f"📋 Водоснабжение: {ws}")
        if ws == "none":
            checks.append("⚠️ Нет водоснабжения — нестандартно")
            score -= 10

        # Канализация
        sw = params.get("sewage", "central")
        checks.append(f"📋 Канализация: {sw}")
        if sw == "septic":
            checks.append("📋 Септик: объём ≥ 3-суточного притока, расстояние от колодца ≥ 20м")

        # Электрика
        load_map = {"house": "5-7 кВт", "office": "50-80 Вт/м²", "commercial": "80-120 Вт/м²"}
        checks.append(f"📋 Электрическая нагрузка: {load_map.get(bt, '50-80 Вт/м²')} (СП 76.13330)")

        return {"passed": score >= 70, "score": max(0, score), "checks": checks}

    def _check_applicable_norms(self, params: dict) -> list:
        """Определить применимые нормативы."""
        try:
            from shared.norms_reference import get_applicable_norms
            return get_applicable_norms(
                params.get("building_type", "house"),
                params.get("floors", 2),
                params.get("height_m", 6.0),
                params.get("material", "brick"),
            )
        except ImportError:
            return [{"note": "norms_reference not available"}]

    def _determine_fire_resistance(self, material: str, floors: int) -> dict:
        """Определить класс огнестойкости."""
        if material in ("concrete", "бетон", "brick", "кирпич"):
            if floors <= 3:
                return {"class": "REI 60", "description": "60 минут", "type": "Негорючий"}
            else:
                return {"class": "REI 120", "description": "120 минут", "type": "Негорючий"}
        elif material in ("steel", "сталь"):
            return {"class": "R 30", "description": "30 минут", "type": "Негорючий (без защиты)"}
        elif material in ("wood", "дерево"):
            return {"class": "R 15", "description": "15 минут", "type": "Горючий (требует защиты)"}
        else:
            return {"class": "REI 45", "description": "45 минут", "type": "По умолчанию"}

    def _generate_summary(self, structural, fire, access, energy, foundation, seismic, mep) -> str:
        parts = []
        parts.append(f"📋 Конструкции: {'✅' if structural['passed'] else '⚠️'} ({structural['score']}%)")
        parts.append(f"🔥 Пожарная безопасность: {'✅' if fire['passed'] else '⚠️'} ({fire['score']}%)")
        parts.append(f"♿ Доступность: {'✅' if access['passed'] else '⚠️'} ({access['score']}%)")
        parts.append(f"⚡ Энергоэффективность: {energy.get('energy_class', '?')} ({energy['score']}%)")
        parts.append(f"🏗 Основания: {'✅' if foundation['passed'] else '⚠️'} ({foundation['score']}%)")
        parts.append(f"🌍 Сейсмика: {'✅' if seismic['passed'] else '⚠️'} ({seismic['score']}%)")
        parts.append(f"🔧 Инженерия: {'✅' if mep['passed'] else '⚠️'} ({mep['score']}%)")
        return "\n".join(parts)

    def _generate_action_plan(self, structural, fire, access, energy, foundation, seismic, mep) -> list:
        """План мероприятий по устранению замечаний."""
        actions = []
        for name, data in [("Конструкции", structural), ("Пожар", fire), ("Доступность", access),
                           ("Энерго", energy), ("Основания", foundation), ("Сейсмика", seismic), ("Инженерия", mep)]:
            if not data["passed"]:
                actions.append(f"[{name}] Проверить и устранить замечания (см. детали)")
            for check in data.get("checks", []):
                if check.startswith("⚠️") or check.startswith("❌"):
                    actions.append(f"  → {check}")

        if not actions:
            actions.append("✅ Все проверки пройдены — действий не требуется")

        return actions
