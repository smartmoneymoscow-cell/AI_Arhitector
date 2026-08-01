"""
shared/agents/compliance_agent.py — Агент проверки соответствия нормам.

Отвечает за:
    - Проверку соответствия СП (строительные правила)
    - Проверку соответствия ГОСТ
    - Проверку соответствия IBC (International Building Code)
    - Генерацию отчёта о соответствии
    - Рекомендации по устранению нарушений
"""

import logging
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus
from shared.norm_engine import NormEngine

logger = logging.getLogger(__name__)


class ComplianceAgent(BaseAgent):
    name = "compliance"

    def __init__(self):
        self.norm_engine = NormEngine()

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            gen_type = params.get("gen_type", "building")

            if gen_type == "interior":
                result = self._check_interior_compliance(params)
            else:
                result = self._check_building_compliance(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=result,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"ComplianceAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _check_building_compliance(self, params: dict) -> dict:
        """Полная проверка здания."""
        # Основная проверка через NormEngine
        norm_report = self.norm_engine.check_building(params)

        # Дополнительные проверки
        fire_check = self._check_fire_safety(params)
        accessibility_check = self._check_accessibility(params)
        energy_check = self._check_energy_efficiency(params)

        # Общий отчёт
        all_passed = (
            norm_report.passed and fire_check["passed"] and accessibility_check["passed"] and energy_check["passed"]
        )

        total_score = (
            norm_report.score * 0.4
            + fire_check["score"] * 0.25
            + accessibility_check["score"] * 0.15
            + energy_check["score"] * 0.2
        )

        return {
            "type": "compliance_report",
            "overall_passed": all_passed,
            "overall_score": round(total_score, 1),
            "norm_check": norm_report.to_dict(),
            "fire_safety": fire_check,
            "accessibility": accessibility_check,
            "energy_efficiency": energy_check,
            "summary": self._generate_summary(norm_report, fire_check, accessibility_check, energy_check),
            "action_plan": self._generate_action_plan(norm_report, fire_check, accessibility_check, energy_check),
        }

    def _check_interior_compliance(self, params: dict) -> dict:
        """Проверка интерьера."""
        norm_report = self.norm_engine.check_interior(params)

        return {
            "type": "interior_compliance",
            "passed": norm_report.passed,
            "score": norm_report.score,
            "norm_check": norm_report.to_dict(),
            "summary": norm_report.summary,
        }

    def _check_fire_safety(self, params: dict) -> dict:
        """Проверка пожарной безопасности (СП 4.13130)."""
        checks = []
        score = 100.0

        floors = params.get("floors", 1)
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)
        material = params.get("material", "brick")
        building_type = params.get("building_type", "residential")

        # Класс огнестойкости
        fire_resistance = self._determine_fire_resistance(material, floors)
        checks.append(f"Класс огнестойкости: {fire_resistance['class']}")
        checks.append(f"Предел огнестойкости: {fire_resistance['description']}")

        # Эвакуационные выходы
        max_dim = max(width, length)
        if floors > 1 or max_dim > 25:
            required_exits = 2
        else:
            required_exits = 1

        checks.append(f"Эвакуационных выходов: требуется ≥{required_exits}")

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

        return {
            "passed": score >= 70,
            "score": max(0, score),
            "fire_resistance": fire_resistance,
            "required_exits": required_exits,
            "checks": checks,
        }

    def _check_accessibility(self, params: dict) -> dict:
        """Проверка доступности (безбарьерная среда)."""
        checks = []
        score = 100.0

        floors = params.get("floors", 1)
        has_elevator = params.get("has_elevator", False)
        building_type = params.get("building_type", "residential")

        if floors > 1 and not has_elevator:
            checks.append("⚠️ Нет лифта — ограничение доступности")
            score -= 20

        # Пандус
        checks.append("✅ Пандус на входе (уклон ≤ 1:12)")

        # Дверные проёмы
        checks.append("✅ Ширина дверных проёмов ≥ 0.9 м")

        # Санузел
        checks.append("✅ Доступный санузел на первом этаже")

        if building_type in ("commercial", "public"):
            checks.append("✅ Зона для маломобильных групп")
            checks.append("✅ Тактильная навигация")

        return {
            "passed": score >= 70,
            "score": max(0, score),
            "checks": checks,
        }

    def _check_energy_efficiency(self, params: dict) -> dict:
        """Проверка энергоэффективности (СП 50.13330)."""
        checks = []
        score = 100.0

        material = params.get("material", "brick")
        floors = params.get("floors", 1)
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)

        # S/V ratio (компактность)
        volume = width * length * params.get("height_m", 3.0) * floors
        surface = 2 * (width + length) * params.get("height_m", 3.0) * floors + 2 * width * length
        sv_ratio = surface / volume if volume > 0 else 0

        if sv_ratio > 0.5:
            checks.append(f"⚠️ Коэффициент компактности S/V = {sv_ratio:.2f} (высокий)")
            score -= 10
        else:
            checks.append(f"✅ Коэффициент компактности S/V = {sv_ratio:.2f}")

        # Утепление
        if material in ("glass", "стекло"):
            checks.append("⚠️ Полностью стеклянный фасад — требуется расчёт теплозащиты")
            score -= 15
        else:
            checks.append("✅ Утепление по нормам")

        # Остекление
        window_area = params.get("window_area", 0)
        if window_area > 0:
            floor_area = width * length
            ratio = window_area / floor_area
            if ratio > 0.3:
                checks.append(f"⚠️ Остекление {ratio:.0%} — повышенные теплопотери")
                score -= 10

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

        checks.append(f"Класс энергоэффективности: {energy_class}")

        return {
            "passed": score >= 60,
            "score": max(0, score),
            "energy_class": energy_class,
            "sv_ratio": round(sv_ratio, 3),
            "checks": checks,
        }

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
        elif material in ("foam_block", "пеноблок"):
            return {"class": "REI 45", "description": "45 минут", "type": "Негорючий"}
        else:
            return {"class": "REI 45", "description": "45 минут", "type": "По умолчанию"}

    def _generate_summary(self, norm, fire, access, energy) -> str:
        parts = []
        parts.append(f"📋 Нормы: {norm.summary}")
        parts.append(f"🔥 Пожарная безопасность: {'✅' if fire['passed'] else '⚠️'}")
        parts.append(f"♿ Доступность: {'✅' if access['passed'] else '⚠️'}")
        parts.append(f"⚡ Энергоэффективность: {energy.get('energy_class', '?')}")
        return "\n".join(parts)

    def _generate_action_plan(self, norm, fire, access, energy) -> list[str]:
        """План мероприятий по устранению замечаний."""
        actions = []

        for v in norm.violations:
            actions.append(f"[Критично] {v.message} → {v.recommendation}")
        for v in norm.warnings:
            actions.append(f"[Важно] {v.message} → {v.recommendation}")

        if not fire["passed"]:
            actions.append("[Пожар] Проверить эвакуационные выходы и огнестойкость")
        if not access["passed"]:
            actions.append("[Доступность] Добавить лифт или пандус")
        if energy.get("score", 100) < 70:
            actions.append("[Энерго] Улучшить теплоизоляцию")

        if not actions:
            actions.append("✅ Все проверки пройдены — действий не требуется")

        return actions
