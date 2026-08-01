"""
shared/agents/research_agent.py — Агент исследований.

Отвечает за:
    - Поиск архитектурных референсов
    - Анализ трендов в архитектуре
    - Изучение аналогичных проектов
    - Сбор информации о материалах и технологиях
"""

import time
import logging
from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    name = "research"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            prompt = task.params.get("prompt", "")
            research_type = task.params.get("type", "general")

            if research_type == "references":
                result = self._find_references(prompt, task.params)
            elif research_type == "trends":
                result = self._analyze_trends(prompt, task.params)
            elif research_type == "materials":
                result = self._research_materials(prompt, task.params)
            elif research_type == "technologies":
                result = self._research_technologies(prompt, task.params)
            else:
                result = self._general_research(prompt, task.params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=result,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"ResearchAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _find_references(self, prompt: str, params: dict) -> dict:
        """Найти архитектурные референсы по описанию."""
        from shared.web_search import get_search_engine
        engine = get_search_engine()

        style = params.get("style", "")
        building_type = params.get("building_type", "house")
        query = f"{style} {building_type} architecture reference design"
        results = engine.search_architecture(query, max_results=10)

        references = []
        for r in results.results:
            references.append({
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
                "source": r.source,
            })

        return {
            "type": "references",
            "query": query,
            "references": references,
            "total": len(references),
            "insights": self._extract_insights(references),
        }

    def _analyze_trends(self, prompt: str, params: dict) -> dict:
        """Анализ трендов в архитектуре."""
        from shared.web_search import get_search_engine
        engine = get_search_engine()

        queries = [
            "архитектурные тренды 2026 жилая недвижимость",
            "современные фасады тренды",
            "экологичное строительство тренды",
        ]
        all_trends = []
        for q in queries:
            results = engine.search_trends(q, max_results=5)
            for r in results.results:
                all_trends.append({
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                })

        return {
            "type": "trends",
            "trends": all_trends[:15],
            "categories": {
                "sustainability": [t for t in all_trends if any(kw in t["title"].lower() for kw in ["eco", "green", "устойчив"])],
                "technology": [t for t in all_trends if any(kw in t["title"].lower() for kw in ["smart", "tech", "digital"])],
                "materials": [t for t in all_trends if any(kw in t["title"].lower() for kw in ["material", "материал"])],
            },
        }

    def _research_materials(self, prompt: str, params: dict) -> dict:
        """Исследование строительных материалов."""
        from shared.web_search import get_search_engine
        engine = get_search_engine()

        material = params.get("material", "кирпич")
        query = f"{material} строительный материал характеристики цена 2026"
        results = engine.search_materials(query, max_results=10)

        return {
            "type": "materials",
            "material": material,
            "sources": [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in results.results
            ],
            "properties": self._infer_material_properties(material),
        }

    def _research_technologies(self, prompt: str, params: dict) -> dict:
        """Исследование строительных технологий."""
        from shared.web_search import get_search_engine
        engine = get_search_engine()

        query = f"современные строительные технологии {prompt}"
        results = engine.search(query, max_results=10)

        return {
            "type": "technologies",
            "technologies": [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in results.results
            ],
        }

    def _general_research(self, prompt: str, params: dict) -> dict:
        """Общее исследование по запросу."""
        from shared.web_search import get_search_engine
        engine = get_search_engine()

        results = engine.search(prompt, max_results=10)
        arch_results = engine.search_architecture(prompt, max_results=5)

        return {
            "type": "general",
            "general_results": [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in results.results
            ],
            "architecture_results": [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in arch_results.results
            ],
            "insights": self._extract_insights([
                {"title": r.title, "snippet": r.snippet}
                for r in results.results
            ]),
        }

    def _extract_insights(self, references: list[dict]) -> list[str]:
        """Извлечь ключевые инсайты из найденных материалов."""
        insights = []
        keywords_count = {}

        for ref in references:
            text = (ref.get("title", "") + " " + ref.get("snippet", "")).lower()
            for kw in ["современный", "минимализм", "экологичный", "энергоэффективный",
                        "smart", "модульный", "параметрический", "биофильный"]:
                if kw in text:
                    keywords_count[kw] = keywords_count.get(kw, 0) + 1

        for kw, count in sorted(keywords_count.items(), key=lambda x: -x[1])[:5]:
            insights.append(f"Часто упоминается: {kw} ({count} раз)")

        return insights

    def _infer_material_properties(self, material: str) -> dict:
        """Свойства материала (из кэша знаний)."""
        props = {
            "кирпич": {"durability": "100+ лет", "thermal": "высокая", "price": "средняя", "eco": "да"},
            "дерево": {"durability": "50-80 лет", "thermal": "высокая", "price": "средняя", "eco": "да"},
            "бетон": {"durability": "100+ лет", "thermal": "низкая", "price": "средняя", "eco": "нет"},
            "пеноблок": {"durability": "50-70 лет", "thermal": "высокая", "price": "низкая", "eco": "да"},
            "стекло": {"durability": "50+ лет", "thermal": "низкая", "price": "высокая", "eco": "средне"},
            "brick": {"durability": "100+ years", "thermal": "high", "price": "medium", "eco": "yes"},
            "wood": {"durability": "50-80 years", "thermal": "high", "price": "medium", "eco": "yes"},
            "concrete": {"durability": "100+ years", "thermal": "low", "price": "medium", "eco": "no"},
        }
        return props.get(material.lower(), {"durability": "unknown", "thermal": "unknown", "price": "unknown"})
