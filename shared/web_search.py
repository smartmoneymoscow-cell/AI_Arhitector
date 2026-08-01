"""
shared/web_search.py — Модуль веб-поиска для архитектурных исследований.

Используется ResearchAgent, MarketAgent, NormEngine и др.

Провайдеры:
    1. DuckDuckGo HTML (бесплатный, без API ключа)
    2. SerpAPI (платный — через SERPAPI_KEY env)

Использование:
    from shared.web_search import WebSearchEngine

    engine = WebSearchEngine()
    results = engine.search("современные тренды архитектуры 2026")
"""

import os
import re
import json
import logging
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Один результат поиска."""
    title: str
    url: str
    snippet: str
    source: str = ""
    published: str = ""


@dataclass
class SearchResponse:
    """Ответ поискового запроса."""
    query: str
    results: list[SearchResult] = field(default_factory=list)
    total: int = 0
    provider: str = "duckduckgo"
    error: Optional[str] = None


class WebSearchEngine:
    """
    Универсальный поисковый движок.

    Провайдеры:
        1. DuckDuckGo HTML (бесплатный, без API ключа)
        2. SerpAPI (платный, надёжный — через SERPAPI_KEY)
    """

    DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"
    SERPAPI_URL = "https://serpapi.com/search"

    ARCH_DOMAINS = [
        "archdaily.com", "dezeen.com", "architecturaldigest.com",
        "archdaily.ru", "architime.ru", "pinterest.com",
        "houzz.com", "behance.net", "planning.org",
    ]

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self.serpapi_key = os.getenv("SERPAPI_KEY", "")

    def search(
        self,
        query: str,
        max_results: int = 10,
        region: str = "ru-ru",
        site_filter: Optional[str] = None,
    ) -> SearchResponse:
        if site_filter:
            query = f"site:{site_filter} {query}"
        if self.serpapi_key:
            return self._search_serpapi(query, max_results, region)
        return self._search_ddg(query, max_results, region)

    def search_architecture(self, query: str, max_results: int = 10) -> SearchResponse:
        """Поиск по архитектурным источникам."""
        arch_sites = " OR ".join(f"site:{d}" for d in self.ARCH_DOMAINS[:5])
        return self.search(f"{query} ({arch_sites})", max_results)

    def search_norms(self, query: str, max_results: int = 10) -> SearchResponse:
        """Поиск по строительным нормам и ГОСТ."""
        return self.search(f"{query} СП ГОСТ строительные нормы", max_results, region="ru-ru")

    def search_materials(self, query: str, max_results: int = 10) -> SearchResponse:
        """Поиск по стройматериалам и ценам."""
        return self.search(f"{query} цена строительные материалы 2026", max_results, region="ru-ru")

    def search_trends(self, query: str, max_results: int = 10) -> SearchResponse:
        """Поиск трендов в архитектуре."""
        return self.search(f"{query} архитектурные тренды 2026", max_results)

    def _search_ddg(self, query: str, max_results: int, region: str) -> SearchResponse:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    self.DUCKDUCKGO_URL,
                    data={"q": query, "kl": region},
                    headers=headers,
                    follow_redirects=True,
                )
                resp.raise_for_status()
            results = self._parse_ddg_html(resp.text, max_results)
            return SearchResponse(query=query, results=results, total=len(results), provider="duckduckgo")
        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")
            return SearchResponse(query=query, error=str(e), provider="duckduckgo")

    def _search_serpapi(self, query: str, max_results: int, region: str) -> SearchResponse:
        try:
            params = {
                "q": query, "api_key": self.serpapi_key,
                "engine": "google", "num": max_results,
                "hl": "ru", "gl": region.split("-")[0],
            }
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(self.SERPAPI_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            results = [
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    source=item.get("displayed_link", ""),
                )
                for item in data.get("organic_results", [])[:max_results]
            ]
            return SearchResponse(query=query, results=results, total=len(results), provider="serpapi")
        except Exception as e:
            logger.warning(f"SerpAPI search failed: {e}")
            return SearchResponse(query=query, error=str(e), provider="serpapi")

    def _parse_ddg_html(self, html: str, max_results: int) -> list[SearchResult]:
        results = []
        blocks = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            html, re.DOTALL,
        )
        for url, title, snippet in blocks[:max_results]:
            title = re.sub(r'<[^>]+>', '', title).strip()
            snippet = re.sub(r'<[^>]+>', '', snippet).strip()
            if "uddg=" in url:
                match = re.search(r'uddg=([^&]+)', url)
                if match:
                    url = urllib.parse.unquote(match.group(1))
            if title and url:
                results.append(SearchResult(title=title, url=url, snippet=snippet))
        return results


_default_engine: Optional[WebSearchEngine] = None


def get_search_engine() -> WebSearchEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = WebSearchEngine()
    return _default_engine
