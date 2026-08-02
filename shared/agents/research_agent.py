"""
shared/agents/research_agent.py — Агент изучения референсов (web search).

v9.0 — Интеграция с DuckDuckGo/SerpAPI для поиска референсов.

Ищет:
- Архитектурные референсы по стилю и типу здания
- Современные тренды в дизайне
- Примеры планировок
- Материалы и технологии
"""

import logging
import os
import time

import httpx

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)

# SerpAPI key (optional)
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")


class ResearchAgent(BaseAgent):
    """Агент поиска архитектурных референсов в интернете."""

    name = "research"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            prompt = params.get("prompt", "")
            style = params.get("style", "")
            building_type = params.get("building_type", "")
            gen_type = params.get("gen_type", "building")

            references = self._search_references(prompt, style, building_type, gen_type)
            trends = self._search_trends(style, gen_type)
            materials = self._search_materials(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data={
                    "references": references,
                    "trends": trends,
                    "materials": materials,
                    "search_queries": self._build_queries(prompt, style, building_type, gen_type),
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"ResearchAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _build_queries(self, prompt: str, style: str, building_type: str, gen_type: str) -> list[str]:
        """Строит поисковые запросы."""
        queries = []

        if gen_type == "interior":
            room = prompt.split()[0] if prompt else "room"
            queries.append(f"{style} {room} interior design reference 2024")
            queries.append(f"{style} interior design ideas {room}")
            queries.append(f"современный дизайн интерьера {style}")
        elif gen_type == "landscape":
            queries.append(f"landscape design {style} garden reference")
            queries.append(f"ландшафтный дизайн {style} сад")
        else:
            queries.append(f"{style} {building_type} architecture reference 2024")
            queries.append(f"{building_type} facade design {style}")
            queries.append(f"{style} архитектура {building_type} фото")

        return queries

    async def _search_ddg(self, query: str, max_results: int = 5) -> list[dict]:
        """Поиск через DuckDuckGo (бесплатный)."""
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                    timeout=10,
                )
                if r.status_code == 200:
                    data = r.json()
                    results = []
                    for item in data.get("RelatedTopics", [])[:max_results]:
                        if isinstance(item, dict) and item.get("Text"):
                            results.append({
                                "title": item.get("Text", "")[:100],
                                "url": item.get("FirstURL", ""),
                                "snippet": item.get("Text", "")[:200],
                            })
                    return results
        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")
        return []

    async def _search_serpapi(self, query: str, max_results: int = 5) -> list[dict]:
        """Поиск через SerpAPI (платный, но более качественный)."""
        if not SERPAPI_KEY:
            return []

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://serpapi.com/search",
                    params={
                        "q": query,
                        "api_key": SERPAPI_KEY,
                        "engine": "google",
                        "num": max_results,
                    },
                    timeout=15,
                )
                if r.status_code == 200:
                    data = r.json()
                    results = []
                    for item in data.get("organic_results", [])[:max_results]:
                        results.append({
                            "title": item.get("title", ""),
                            "url": item.get("link", ""),
                            "snippet": item.get("snippet", ""),
                            "image": item.get("thumbnail", ""),
                        })
                    return results
        except Exception as e:
            logger.warning(f"SerpAPI search failed: {e}")
        return []

    def _search_references(self, prompt: str, style: str, building_type: str, gen_type: str) -> list[dict]:
        """Поиск референсов (синхронная обёртка)."""
        import asyncio

        queries = self._build_queries(prompt, style, building_type, gen_type)
        all_results = []

        for query in queries[:2]:  # Limit to 2 queries
            try:
                loop = asyncio.new_event_loop()
                results = loop.run_until_complete(self._search_ddg(query))
                loop.close()
                all_results.extend(results)
            except Exception:
                pass

        # Deduplicate by URL
        seen = set()
        unique = []
        for r in all_results:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique.append(r)

        return unique[:10]

    def _search_trends(self, style: str, gen_type: str) -> list[str]:
        """Определение трендов (на основе знаний)."""
        trends = {
            "modern": ["Биофильный дизайн", "Умный дом", "Эко-материалы", "Панорамное остекление"],
            "classic": ["Неоклассика", "Современная классика", "Ар-деко элементы"],
            "loft": ["Индустриальный шик", "Кирпичные акценты", "Металл+дерево"],
            "minimalist": ["Японский минимализм", "Wabi-sabi", "Встроенная мебель"],
            "scandinavian": ["Хюгге", "Светлое дерево", "Текстиль"],
        }
        return trends.get(style, ["Современные материалы", "Энергоэффективность", "Умные технологии"])

    def _search_materials(self, params: dict) -> list[dict]:
        """Рекомендации по материалам."""
        material = params.get("material", "plaster")
        recommendations = {
            "brick": [
                {"name": "Керамический кирпич", "pros": "Прочность, экологичность", "price": "4500 ₽/м²"},
                {"name": "Силикатный кирпич", "pros": "Дешевле, звукоизоляция", "price": "3200 ₽/м²"},
            ],
            "wood": [
                {"name": "Клеёный брус", "pros": "Без усадки, точность", "price": "8000 ₽/м²"},
                {"name": "Оцилиндрованное бревно", "pros": "Экология, тепло", "price": "5500 ₽/м²"},
            ],
            "concrete": [
                {"name": "Монолитный ЖБК", "pros": "Прочность, гибкость форм", "price": "6000 ₽/м²"},
                {"name": "Газобетон", "pros": "Тепло, лёгкость", "price": "2800 ₽/м²"},
            ],
        }
        return recommendations.get(material, [{"name": material, "pros": "По расчёту", "price": "N/A"}])
