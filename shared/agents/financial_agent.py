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

    # ═══ Расширения: DCF, sensitivity, stress test, господдержка ═══

    def calculate_dcf(self, params: dict) -> dict:
        """DCF-анализ (Discounted Cash Flow) на 10–15 лет."""
        capex = params.get("capex_rub", 100_000_000)
        annual_revenue = params.get("annual_revenue_rub", 30_000_000)
        annual_opex = params.get("annual_opex_rub", 15_000_000)
        discount_rate = params.get("discount_rate_pct", 10) / 100
        years = params.get("years", 12)
        revenue_growth = params.get("revenue_growth_pct", 5) / 100
        opex_growth = params.get("opex_growth_pct", 3) / 100
        ramp_up = params.get("ramp_up_years", 3)  # Годы выхода на мощность
        ramp_up_pcts = [0.3, 0.55, 0.75, 0.85, 0.90, 0.95]  # Загрузка по годам

        cash_flows = [-capex]
        details = []
        cumulative = -capex

        for year in range(1, years + 1):
            # Ramp-up factor
            if year <= ramp_up:
                load_factor = ramp_up_pcts[year - 1]
            else:
                load_factor = min(1.0, ramp_up_pcts[-1] + (year - ramp_up) * 0.02)

            rev = annual_revenue * load_factor * (1 + revenue_growth) ** (year - 1)
            opex = annual_opex * (1 + opex_growth) ** (year - 1)
            ebitda = rev - opex

            # Амортизация (линейная, 20 лет)
            depreciation = capex / 20
            profit_before_tax = ebitda - depreciation
            tax = max(0, profit_before_tax * 0.20)  # Налог на прибыль 20%
            net_profit = profit_before_tax - tax

            # FCF = EBITDA - Tax (упрощённо)
            fcf = ebitda - tax
            discounted = fcf / (1 + discount_rate) ** year
            cash_flows.append(round(discounted))
            cumulative += discounted

            details.append({
                "year": year,
                "load_pct": round(load_factor * 100),
                "revenue": round(rev),
                "opex": round(opex),
                "ebitda": round(ebitda),
                "depreciation": round(depreciation),
                "net_profit": round(net_profit),
                "fcf": round(fcf),
                "discounted_fcf": round(discounted),
                "cumulative_npv": round(cumulative),
            })

        # NPV
        npv = sum(cash_flows)

        # IRR (бинарный поиск)
        irr = self._calculate_irr(cash_flows)

        # Payback period
        payback = None
        for d in details:
            if d["cumulative_npv"] >= 0:
                payback = d["year"]
                break

        # DSCR (Debt Service Coverage Ratio)
        annual_debt_service = capex * 0.10  # Примерно 10% от CAPEX в год
        dscr = details[-1]["ebitda"] / annual_debt_service if annual_debt_service > 0 else 0

        return {
            "npv": round(npv),
            "irr_pct": round(irr * 100, 2),
            "payback_years": payback,
            "dscr": round(dscr, 2),
            "cash_flows": details,
            "wacc_pct": round(discount_rate * 100),
            "recommendation": "✅ Проект эффективен" if npv > 0 and irr > discount_rate else "❌ Проект неэффективен",
        }

    def sensitivity_analysis(self, params: dict) -> dict:
        """Sensitivity analysis: ключевые параметры ±20%."""
        base_params = dict(params)
        base_result = self.calculate_dcf(base_params)
        base_npv = base_result["npv"]
        base_irr = base_result["irr_pct"]

        variations = [-20, -10, 0, 10, 20]
        factors = ["revenue", "opex", "capex"]

        results = {}
        for factor in factors:
            factor_results = []
            for pct in variations:
                test_params = dict(base_params)
                if factor == "revenue":
                    test_params["annual_revenue_rub"] = base_params["annual_revenue_rub"] * (1 + pct / 100)
                elif factor == "opex":
                    test_params["annual_opex_rub"] = base_params["annual_opex_rub"] * (1 + pct / 100)
                elif factor == "capex":
                    test_params["capex_rub"] = base_params["capex_rub"] * (1 + pct / 100)

                r = self.calculate_dcf(test_params)
                factor_results.append({
                    "change_pct": pct,
                    "npv": r["npv"],
                    "irr_pct": r["irr_pct"],
                    "payback_years": r["payback_years"],
                })
            results[factor] = factor_results

        return {
            "base_npv": base_npv,
            "base_irr": base_irr,
            "sensitivity": results,
            "most_sensitive": max(results.keys(), key=lambda k: abs(results[k][-1]["npv"] - results[k][0]["npv"])),
        }

    def stress_test(self, params: dict) -> dict:
        """Стресс-тест: экстремальные сценарии."""
        scenarios = {
            "base": dict(params),
            "low_occupancy": dict(params, **{"annual_revenue_rub": params["annual_revenue_rub"] * 0.4}),
            "high_capex": dict(params, **{"capex_rub": params["capex_rub"] * 1.5}),
            "revenue_stagnation": dict(params, **{"revenue_growth_pct": 0}),
            "combined_stress": dict(params, **{
                "annual_revenue_rub": params["annual_revenue_rub"] * 0.4,
                "capex_rub": params["capex_rub"] * 1.3,
                "revenue_growth_pct": 0,
            }),
        }

        results = {}
        for name, p in scenarios.items():
            r = self.calculate_dcf(p)
            results[name] = {
                "npv": r["npv"],
                "irr_pct": r["irr_pct"],
                "payback_years": r["payback_years"],
                "viable": r["npv"] > 0,
            }

        return {
            "scenarios": results,
            "survives_stress": results["combined_stress"]["viable"],
            "recommendation": (
                "✅ Проект устойчив к стрессам" if results["combined_stress"]["viable"]
                else "⚠️ Проект уязвим — рассмотрите снижение CAPEX или увеличение загрузки"
            ),
        }

    def _calculate_irr(self, cash_flows: list[float], tolerance: float = 0.0001) -> float:
        """IRR методом бинарного поиска."""
        low, high = -0.5, 1.0
        for _ in range(100):
            mid = (low + high) / 2
            npv = sum(cf / (1 + mid) ** i for i, cf in enumerate(cash_flows))
            if abs(npv) < tolerance:
                return mid
            if npv > 0:
                low = mid
            else:
                high = mid
        return (low + high) / 2

    def validate_model(self, params: dict) -> dict:
        """Валидация финансовой модели: проверка ключевых метрик."""
        result = self.calculate_dcf(params)
        checks = []
        passed = True

        # NPV > 0
        if result["npv"] <= 0:
            checks.append(f"❌ NPV = {result['npv']:,.0f} ₽ ≤ 0 — проект неэффективен")
            passed = False
        else:
            checks.append(f"✅ NPV = {result['npv']:,.0f} ₽ > 0")

        # IRR > WACC
        wacc = params.get("discount_rate_pct", 10)
        if result["irr_pct"] <= wacc:
            checks.append(f"❌ IRR {result['irr_pct']}% ≤ WACC {wacc}%")
            passed = False
        else:
            checks.append(f"✅ IRR {result['irr_pct']}% > WACC {wacc}%")

        # DSCR > 1.2
        if result["dscr"] < 1.2:
            checks.append(f"⚠️ DSCR {result['dscr']} < 1.2 — кредит может не обслуживаться")
        else:
            checks.append(f"✅ DSCR {result['dscr']} > 1.2")

        # Payback < 10 лет
        payback = result.get("payback_years")
        if payback and payback > 10:
            checks.append(f"⚠️ Окупаемость {payback} лет > 10 лет")
        elif payback:
            checks.append(f"✅ Окупаемость {payback} лет")

        return {
            "passed": passed,
            "checks": checks,
            "metrics": {"npv": result["npv"], "irr": result["irr_pct"], "dscr": result["dscr"], "payback": result["payback_years"]},
        }
