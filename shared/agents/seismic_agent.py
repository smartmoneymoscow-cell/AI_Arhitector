"""
shared/agents/seismic_agent.py — Агент сейсмического анализа

Выполняет:
  - Спектр реакции (СП 14.13330)
  - Сейсмическая сила
  - Динамический коэффициент
  - Проверка конструктивных мер
"""

import logging
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class SeismicAgent(BaseAgent):
    name = "seismic"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            result = self._analyze_seismic(params)
            return TaskResult(status=TaskStatus.DONE, data=result, duration_ms=(time.time() - start) * 1000)
        except Exception as e:
            logger.error(f"SeismicAgent error: {e}")
            return TaskResult(status=TaskStatus.FAILED, error=str(e), duration_ms=(time.time() - start) * 1000)

    def _analyze_seismic(self, params: dict) -> dict:
        """Полный сейсмический анализ."""
        try:
            from shared.structural_analysis import DynamicsAnalyzer
        except ImportError:
            return {"error": "structural_analysis module not available", "status": "skipped"}

        da = DynamicsAnalyzer()
        result = {"type": "seismic_analysis", "checks": {}}

        seismic_zone = int(params.get("seismic_zone", 0))
        if seismic_zone == 0:
            return {
                "type": "seismic_analysis",
                "status": "not_applicable",
                "reason": "Зона не сейсмическая",
            }

        soil = params.get("soil_type", "II")
        T = params.get("period_s", 0.5)
        mass = params.get("total_mass_kg", 50000)

        # Спектр реакции
        result["checks"]["response_spectrum"] = da.response_spectrum(T, soil_type=soil, seismic_zone=seismic_zone)

        # Сейсмическая сила
        K1_map = {5: 0.25, 6: 0.25, 7: 0.5, 8: 0.75, 9: 1.0}
        K1 = K1_map.get(seismic_zone, 0.5)
        beta = result["checks"]["response_spectrum"]["beta"]
        result["checks"]["seismic_force"] = da.seismic_force(mass, K1=K1, beta=beta)

        # Динамический коэффициент
        result["checks"]["dynamic_amplification"] = da.dynamic_amplification_factor(T, 0.3)

        # Рекомендации
        recommendations = []
        if seismic_zone >= 7:
            recommendations.append("Сейсмостойкие швы при перепаде высот >10м")
            recommendations.append("Рамно-связевая или трубчатая конструктивная система")
        if soil in ("IV", "V"):
            recommendations.append("Усиление основания или применение свай")
        if seismic_zone >= 8:
            recommendations.append("Динамический расчёт методом модального анализа")
        if not recommendations:
            recommendations.append("Стандартных мер достаточно")

        result["recommendations"] = recommendations
        result["summary"] = {
            "seismic_zone": seismic_zone,
            "soil_type": soil,
            "K1": K1,
            "beta": beta,
            "seismic_force_kN": result["checks"]["seismic_force"]["seismic_force_kN"],
        }

        return result
