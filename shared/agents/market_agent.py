"""
shared/agents/market_agent.py — Агент анализа рынка.

Отвечает за:
    - Анализ рынка недвижимости
    - Сравнение с конкурентными проектами
    - Оценка спроса на тип здания
    - Ценовые ориентиры
"""

import logging
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class MarketAgent(BaseAgent):
    name = "market"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            analysis_type = task.params.get("type", "full")
            prompt = task.params.get("prompt", "")

            if analysis_type == "competition":
                result = self._analyze_competition(prompt, task.params)
            elif analysis_type == "demand":
                result = self._analyze_demand(prompt, task.params)
            elif analysis_type == "pricing":
                result = self._analyze_pricing(prompt, task.params)
            else:
                result = self._full_analysis(prompt, task.params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=result,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"MarketAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _full_analysis(self, prompt: str, params: dict) -> dict:
        """Полный рыночный анализ."""
        from shared.web_search import get_search_engine

        engine = get_search_engine()

        building_type = params.get("building_type", "house")
        region = params.get("region", "Москва")

        # Поиск рыночных данных
        market_q = f"рынок недвижимости {region} {building_type} 2026 тренд"
        market_results = engine.search(market_q, max_results=8)

        # Ценовые данные
        price_q = f"цена {building_type} {region} за м2 2026"
        price_results = engine.search(price_q, max_results=5)

        # Конкуренты
        comp_q = f"проекты {building_type} {region} архитектура"
        comp_results = engine.search_architecture(comp_q, max_results=5)

        return {
            "type": "full_market_analysis",
            "region": region,
            "building_type": building_type,
            "market_overview": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in market_results.results],
            "pricing_data": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in price_results.results],
            "competitors": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in comp_results.results],
            "market_signals": self._analyze_market_signals(market_results.results),
            "recommendations": self._generate_recommendations(params),
        }

    def _analyze_competition(self, prompt: str, params: dict) -> dict:
        """Анализ конкурентных проектов."""
        from shared.web_search import get_search_engine

        engine = get_search_engine()

        style = params.get("style", "modern")
        building_type = params.get("building_type", "house")
        query = f"{style} {building_type} architecture project award-winning"
        results = engine.search_architecture(query, max_results=10)

        competitors = []
        for r in results.results:
            competitors.append(
                {
                    "name": r.title,
                    "url": r.url,
                    "description": r.snippet,
                    "strengths": self._infer_strengths(r.snippet),
                }
            )

        return {
            "type": "competition",
            "competitors": competitors,
            "competitive_advantages": self._identify_advantages(competitors, params),
        }

    def _analyze_demand(self, prompt: str, params: dict) -> dict:
        """Анализ спроса."""
        from shared.web_search import get_search_engine

        engine = get_search_engine()

        building_type = params.get("building_type", "house")
        query = f"спрос {building_type} недвижимость 2026 тренд"
        results = engine.search(query, max_results=8)

        return {
            "type": "demand",
            "demand_data": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results.results],
            "demand_score": self._estimate_demand_score(params),
            "target_audience": self._identify_target_audience(params),
        }

    def _analyze_pricing(self, prompt: str, params: dict) -> dict:
        """Анализ цен."""
        from shared.cost_engine import CostEngine

        engine = CostEngine()
        estimate = engine.calculate(params)

        return {
            "type": "pricing",
            "cost_estimate": estimate.to_dict(),
            "price_per_m2": estimate.cost_per_m2,
            "market_position": self._determine_market_position(estimate.cost_per_m2),
        }

    def _analyze_market_signals(self, results: list) -> list[str]:
        signals = []
        for r in results:
            text = (r.title + " " + r.snippet).lower()
            if any(kw in text for kw in ["рост", "increase", "спрос", "demand"]):
                signals.append(f"📈 Позитивный сигнал: {r.title}")
            elif any(kw in text for kw in ["спад", "decline", "кризис", "crisis"]):
                signals.append(f"📉 Негативный сигнал: {r.title}")
        return signals[:5]

    def _generate_recommendations(self, params: dict) -> list[str]:
        recs = []
        style = params.get("style", "modern")
        building_type = params.get("building_type", "house")

        recs.append(f"Стиль '{style}' в тренде — рекомендуется к реализации")
        if building_type in ("house", "cottage"):
            recs.append("Частные дома — стабильный спрос в сегменте премиум")
        recs.append("Рекомендуется добавить smart-home функционал для повышения ценности")
        recs.append("Энергоэффективность — ключевой фактор для покупателей 2026")

        return recs

    def _infer_strengths(self, text: str) -> list[str]:
        strengths = []
        text_lower = text.lower()
        if "award" in text_lower or "наград" in text_lower:
            strengths.append("Награждённый проект")
        if "sustainable" in text_lower or "eco" in text_lower:
            strengths.append("Экологичность")
        if "innovative" in text_lower or "инновац" in text_lower:
            strengths.append("Инновационность")
        return strengths or ["Известный проект"]

    def _identify_advantages(self, competitors: list, params: dict) -> list[str]:
        return [
            "AI-генерация позволяет быстро протестировать десятки вариантов",
            "Параметрический дизайн — точная настройка под клиента",
            "Автоматическая проверка норм (NormEngine) — юридическая чистота",
        ]

    def _estimate_demand_score(self, params: dict) -> float:
        """Оценка спроса 0-100."""
        score = 50.0
        building_type = params.get("building_type", "house")
        if building_type in ("house", "cottage"):
            score += 15
        if params.get("style") in ("modern", "современный", "minimalist"):
            score += 10
        if params.get("floors", 1) <= 3:
            score += 5
        return min(100, score)

    def _identify_target_audience(self, params: dict) -> list[str]:
        building_type = params.get("building_type", "house")
        if building_type in ("house", "cottage"):
            return ["Семьи 30-50 лет", "Инвесторы в загородную недвижимость", "IT-специалисты (удалёнка)"]
        elif building_type in ("office", "commercial"):
            return ["Стартапы", "Малый бизнес", "Коворкинги"]
        return ["Частные застройщики"]

    def _determine_market_position(self, price_per_m2: float) -> str:
        if price_per_m2 < 50000:
            return "Эконом-сегмент"
        elif price_per_m2 < 100000:
            return "Комфорт-сегмент"
        elif price_per_m2 < 200000:
            return "Бизнес-сегмент"
        else:
            return "Премиум-сегмент"
