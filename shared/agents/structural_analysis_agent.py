"""
shared/agents/structural_analysis_agent.py — Агент структурного анализа (МКЭ)

Выполняет:
  - Расчёт МКЭ (балки, рамы, фермы)
  - Проверка стальных элементов (СП 16.13330)
  - Проверка ЖБ элементов (СП 63.13330)
  - Комбинации нагрузок (СП 20.13330)
  - База сечений проката
"""

import logging
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class StructuralAnalysisAgent(BaseAgent):
    name = "structural_analysis"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            result = self._run_analysis(params)
            return TaskResult(status=TaskStatus.DONE, data=result, duration_ms=(time.time() - start) * 1000)
        except Exception as e:
            logger.error(f"StructuralAnalysisAgent error: {e}")
            return TaskResult(status=TaskStatus.FAILED, error=str(e), duration_ms=(time.time() - start) * 1000)

    def _run_analysis(self, params: dict) -> dict:
        """Запуск полного структурного анализа."""
        try:
            from shared.structural_analysis import StructuralEngine  # noqa: F401
        except ImportError:
            return {"error": "structural_analysis module not available", "status": "skipped"}

        engine = StructuralEngine()
        results = {"type": "structural_analysis", "checks": {}}

        # 1. Комбинации нагрузок
        dead = params.get("dead_load_kN_m2", 5.0)
        live = params.get("live_load_kN_m2", 2.0)
        snow = params.get("snow_load_kN_m2", 1.8)
        wind = params.get("wind_load_kN_m2", 0.4)
        results["checks"]["load_combinations"] = engine.loads.basic_combination(dead, live, snow, wind)

        # 2. Проверка балки (если данные есть)
        if params.get("beam_span_m"):
            L = params["beam_span_m"]
            Wx = params.get("beam_Wx_m3", 0.0005)
            fy = params.get("steel_f_y_MPa", 345)
            results["checks"]["beam_bending"] = engine.checker.steel_beam_bending(Wx, fy)
            results["checks"]["deflection"] = engine.checker.deflection_check(L, L / 300)

        # 3. Сейсмика
        seismic_zone = params.get("seismic_zone", 0)
        if seismic_zone and seismic_zone not in (0, "none"):
            T = params.get("period_s", 0.5)
            results["checks"]["response_spectrum"] = engine.dynamics.response_spectrum(
                T, soil_type=params.get("soil_type", "II"), seismic_zone=int(seismic_zone)
            )
            results["checks"]["seismic_force"] = engine.dynamics.seismic_force(params.get("total_mass_kg", 50000))

        # 4. Устойчивость
        if params.get("column_L_eff_m"):
            E = 206000 if params.get("material") == "steel" else 30000
            I = params.get("column_I_m4", 0.00001)
            results["checks"]["euler_buckling"] = engine.stability.euler_buckling_load(E, I, params["column_L_eff_m"])

        # 5. Основание
        soil = params.get("soil_type", "III")
        results["checks"]["foundation"] = engine.foundation.bearing_capacity_sand(
            soil, params.get("foundation_depth_m", 1.2), params.get("width_m", 10)
        )

        # 6. Сводка
        results["summary"] = {
            "checks_performed": len(results["checks"]),
            "structural_system": params.get("structural_system", "frame"),
            "material": params.get("material", "unknown"),
        }

        return results
