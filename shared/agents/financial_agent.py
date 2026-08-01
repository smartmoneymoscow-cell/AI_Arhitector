"""
shared/agents/financial_agent.py — Агент финансовой оценки.

Отвечает за:
    - Расчёт стоимости строительства
    - Оценку ROI (возврат инвестиций)
    - Анализ окупаемости
    - Сравнение вариантов инвестирования
    - Прогноз стоимости недвижимости
"""

import logging
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class FinancialAgent(BaseAgent):
    name = "financial"

    # Рыночные данные (руб/м², средние по Москве 2026)
    MARKET_PRICES = {
        "house": {"min": 80000, "avg": 150000, "max": 400000},
        "cottage": {"min": 100000, "avg": 200000, "max": 600000},
        "villa": {"min": 200000, "avg": 500000, "max": 1500000},
        "apartment": {"min": 120000, "avg": 250000, "max": 800000},
        "office": {"min": 100000, "avg": 200000, "max": 500000},
        "commercial": {"min": 80000, "avg": 180000, "max": 600000},
    }

    # Доходность аренды (% годовых)
    RENTAL_YIELDS = {
        "house": 4.5,
        "cottage": 5.0,
        "villa": 3.5,
        "apartment": 5.5,
        "office": 7.0,
        "commercial": 8.0,
    }

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            analysis_type = params.get("type", "full")

            if analysis_type == "roi":
                result = self._calculate_roi(params)
            elif analysis_type == "payback":
                result = self._calculate_payback(params)
            elif analysis_type == "comparison":
                result = self._compare_options(params)
            else:
                result = self._full_analysis(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=result,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"FinancialAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _full_analysis(self, params: dict) -> dict:
        """Полный финансовый анализ."""
        from shared.cost_engine import CostEngine

        cost_engine = CostEngine()

        # Расчёт стоимости строительства
        cost_estimate = cost_engine.calculate(params)
        construction_cost = cost_estimate.total

        # Рыночная стоимость
        building_type = params.get("building_type", "house")
        total_area = params.get("width_m", 10) * params.get("length_m", 10) * params.get("floors", 1)
        market_value = self._estimate_market_value(total_area, building_type, params)

        # ROI
        roi = self._compute_roi(construction_cost, market_value)

        # Окупаемость через аренду
        rental_yield = self.RENTAL_YIELDS.get(building_type, 5.0)
        annual_rent = market_value * rental_yield / 100
        payback_years = construction_cost / annual_rent if annual_rent > 0 else float("inf")

        # Прогноз роста стоимости
        appreciation = self._forecast_appreciation(building_type, params)

        return {
            "type": "financial_analysis",
            "construction_cost": round(construction_cost),
            "market_value": round(market_value),
            "roi_pct": round(roi, 1),
            "rental_yield_pct": rental_yield,
            "annual_rental_income": round(annual_rent),
            "payback_years": round(payback_years, 1),
            "cost_per_m2": round(construction_cost / total_area) if total_area > 0 else 0,
            "market_price_per_m2": round(market_value / total_area) if total_area > 0 else 0,
            "appreciation_forecast": appreciation,
            "breakdown": cost_estimate.to_dict(),
            "investment_score": self._calculate_investment_score(roi, payback_years, appreciation),
            "recommendations": self._generate_recommendations(roi, payback_years, params),
        }

    def _calculate_roi(self, params: dict) -> dict:
        """Расчёт ROI."""
        from shared.cost_engine import CostEngine

        cost_engine = CostEngine()
        cost_estimate = cost_engine.calculate(params)
        construction_cost = cost_estimate.total

        building_type = params.get("building_type", "house")
        total_area = params.get("width_m", 10) * params.get("length_m", 10) * params.get("floors", 1)
        market_value = self._estimate_market_value(total_area, building_type, params)

        roi = self._compute_roi(construction_cost, market_value)

        return {
            "type": "roi",
            "construction_cost": round(construction_cost),
            "market_value": round(market_value),
            "roi_pct": round(roi, 1),
            "profit": round(market_value - construction_cost),
            "verdict": "Прибыльно ✅" if roi > 0 else "Убыточно ❌",
        }

    def _calculate_payback(self, params: dict) -> dict:
        """Расчёт окупаемости."""
        from shared.cost_engine import CostEngine

        cost_engine = CostEngine()
        cost_estimate = cost_engine.calculate(params)

        building_type = params.get("building_type", "house")
        total_area = params.get("width_m", 10) * params.get("length_m", 10) * params.get("floors", 1)
        market_value = self._estimate_market_value(total_area, building_type, params)

        rental_yield = self.RENTAL_YIELDS.get(building_type, 5.0)
        annual_rent = market_value * rental_yield / 100
        monthly_rent = annual_rent / 12

        payback_years = cost_estimate.total / annual_rent if annual_rent > 0 else float("inf")

        return {
            "type": "payback",
            "total_investment": round(cost_estimate.total),
            "monthly_rental": round(monthly_rent),
            "annual_rental": round(annual_rent),
            "payback_years": round(payback_years, 1),
            "rental_yield_pct": rental_yield,
            "cash_flow": self._project_cash_flow(cost_estimate.total, annual_rent, 10),
        }

    def _compare_options(self, params: dict) -> dict:
        """Сравнение вариантов."""
        from shared.cost_engine import CostEngine

        cost_engine = CostEngine()

        building_type = params.get("building_type", "house")
        total_area = params.get("width_m", 10) * params.get("length_m", 10) * params.get("floors", 1)

        options = []
        for material in ["brick", "wood", "concrete", "foam_block"]:
            variant_params = {**params, "material": material}
            cost = cost_engine.calculate(variant_params)
            market_value = self._estimate_market_value(total_area, building_type, variant_params)
            roi = self._compute_roi(cost.total, market_value)

            options.append(
                {
                    "material": material,
                    "construction_cost": round(cost.total),
                    "market_value": round(market_value),
                    "roi_pct": round(roi, 1),
                    "cost_per_m2": round(cost.total / total_area) if total_area > 0 else 0,
                }
            )

        best = max(options, key=lambda x: x["roi_pct"])

        return {
            "type": "comparison",
            "options": options,
            "best_option": best,
            "recommendation": f"Лучший вариант: {best['material']} (ROI {best['roi_pct']}%)",
        }

    def _estimate_market_value(self, area_m2: float, building_type: str, params: dict) -> float:
        """Оценка рыночной стоимости."""
        prices = self.MARKET_PRICES.get(building_type, self.MARKET_PRICES["house"])
        style = params.get("style", "modern")

        # Базовая цена за м²
        base_price = prices["avg"]

        # Корректировка на стиль
        style_multipliers = {
            "luxury": 1.5,
            "люкс": 1.5,
            "премиум": 1.5,
            "modern": 1.1,
            "современный": 1.1,
            "classic": 1.2,
            "классический": 1.2,
            "minimalist": 1.0,
            "минимализм": 1.0,
            "eco": 1.15,
            "биофильный": 1.15,
        }
        mult = style_multipliers.get(style.lower(), 1.0)

        return area_m2 * base_price * mult

    def _compute_roi(self, cost: float, market_value: float) -> float:
        """ROI в процентах."""
        if cost <= 0:
            return 0
        return ((market_value - cost) / cost) * 100

    def _forecast_appreciation(self, building_type: str, params: dict) -> dict:
        """Прогноз роста стоимости."""
        # Среднегодовой рост стоимости недвижимости
        annual_growth = {
            "house": 5.0,
            "cottage": 6.0,
            "villa": 4.0,
            "apartment": 7.0,
            "office": 5.0,
            "commercial": 5.5,
        }
        growth = annual_growth.get(building_type, 5.0)

        return {
            "annual_growth_pct": growth,
            "5_year_growth_pct": round(((1 + growth / 100) ** 5 - 1) * 100, 1),
            "10_year_growth_pct": round(((1 + growth / 100) ** 10 - 1) * 100, 1),
        }

    def _calculate_investment_score(self, roi: float, payback_years: float, appreciation: dict) -> float:
        """Инвестиционный балл 0-100."""
        score = 50.0

        # ROI
        if roi > 30:
            score += 20
        elif roi > 10:
            score += 10
        elif roi < 0:
            score -= 20

        # Окупаемость
        if payback_years < 10:
            score += 15
        elif payback_years < 15:
            score += 5
        elif payback_years > 25:
            score -= 10

        # Рост стоимости
        growth_5y = appreciation.get("5_year_growth_pct", 0)
        if growth_5y > 30:
            score += 15
        elif growth_5y > 15:
            score += 5

        return max(0, min(100, score))

    def _generate_recommendations(self, roi: float, payback_years: float, params: dict) -> list[str]:
        recs = []
        if roi > 20:
            recs.append("✅ Высокая рентабельность — рекомендуется к реализации")
        elif roi > 0:
            recs.append("⚠️ Умеренная рентабельность — рассмотрите оптимизацию затрат")
        else:
            recs.append("❌ Отрицательный ROI — необходим пересмотр проекта")

        if payback_years > 20:
            recs.append("💡 Долгая окупаемость — рассмотрите краткосрочную аренду")

        recs.append("📊 Рекомендуется провести оценку земельного участка")
        recs.append("📋 Получить точную смету у подрядчика")

        return recs

    def _project_cash_flow(self, investment: float, annual_income: float, years: int) -> list[dict]:
        """Прогноз денежного потока."""
        cash_flow = []
        cumulative = -investment
        for year in range(1, years + 1):
            cumulative += annual_income
            cash_flow.append(
                {
                    "year": year,
                    "income": round(annual_income),
                    "cumulative": round(cumulative),
                    "break_even": cumulative >= 0,
                }
            )
        return cash_flow
