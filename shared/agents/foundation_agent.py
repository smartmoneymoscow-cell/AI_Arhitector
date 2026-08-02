"""
shared/agents/foundation_agent.py — Агент расчёта оснований и фундаментов

Выполняет:
  - Несущая способность грунта (СП 22.13330)
  - Несущая способность свай (СП 24.13330)
  - Осадка фундамента
  - Подбор типа фундамента
"""

import logging
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class FoundationAgent(BaseAgent):
    name = "foundation"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            result = self._analyze_foundation(params)
            return TaskResult(status=TaskStatus.DONE, data=result, duration_ms=(time.time() - start) * 1000)
        except Exception as e:
            logger.error(f"FoundationAgent error: {e}")
            return TaskResult(status=TaskStatus.FAILED, error=str(e), duration_ms=(time.time() - start) * 1000)

    def _analyze_foundation(self, params: dict) -> dict:
        """Анализ основания и подбор фундамента."""
        try:
            from shared.structural_analysis import FoundationAnalyzer
        except ImportError:
            return {"error": "structural_analysis module not available", "status": "skipped"}

        fa = FoundationAnalyzer()
        result = {"type": "foundation_analysis", "checks": {}}

        soil = params.get("soil_type", "III")
        width = params.get("width_m", 10)
        length = params.get("length_m", 12)
        floors = params.get("floors", 2)
        ft = params.get("foundation_type", "strip")
        depth = params.get("foundation_depth_m", 1.2)

        # Несущая способность грунта
        result["checks"]["bearing_capacity"] = fa.bearing_capacity_sand(soil, depth, width)

        # Осадка
        R = result["checks"]["bearing_capacity"]["R_kPa"]
        E0 = {"I": 50, "II": 15, "III": 8, "IV": 5, "V": 3}.get(soil, 8)
        total_load = floors * width * length * 15  # ~15 кН/м² на этаж
        area = width * length
        load_per_m2 = total_load / area if area > 0 else 0
        result["checks"]["settlement"] = fa.settlement_estimate(R, E0, width, load_per_m2)

        # Сваи (если свайный фундамент)
        if ft == "pile":
            pile_d = params.get("pile_diameter_m", 0.3)
            pile_l = params.get("pile_length_m", 6.0)
            result["checks"]["pile_capacity"] = fa.pile_capacity(pile_d, pile_l, soil)
            result["checks"]["pile_spacing"] = fa.pile_spacing(pile_d)

        # Рекомендации
        recommendations = []
        if ft == "strip" and soil in ("IV", "V"):
            recommendations.append("Для слабых грунтов рекомендуется плитный или свайный фундамент")
        if ft == "strip" and floors > 3:
            recommendations.append(f"Для {floors}-этажного здания рекомендуется усиленный фундамент")
        if not recommendations:
            recommendations.append("Тип фундамента соответствует условиям")

        result["recommendations"] = recommendations
        result["summary"] = {
            "soil_type": soil,
            "foundation_type": ft,
            "R_kPa": R,
            "floors": floors,
        }

        return result
