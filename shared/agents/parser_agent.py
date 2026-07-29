"""
shared/agents/parser_agent.py — Агент парсинга промтов.

Отвечает за:
- Парсинг естественного языка → структурированные параметры
- LLM вызов с fallback на regex
- Валидацию и нормализацию параметров
- Определение типа генерации (building/interior)
"""

import time
from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus
from shared.parser import fallback_regex_parse, parse_prompt_sync
from shared.validation import validate_params


class ParserAgent(BaseAgent):
    name = "parser"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            prompt = task.params.get("prompt", "")
            use_llm = task.params.get("use_llm", True)

            if use_llm:
                try:
                    raw_params = parse_prompt_sync(prompt)
                except Exception:
                    raw_params = fallback_regex_parse(prompt)
            else:
                raw_params = fallback_regex_parse(prompt)

            params = validate_params(raw_params)

            # Определяем тип генерации
            gen_type = self._detect_type(prompt, params)

            duration = (time.time() - start) * 1000
            return TaskResult(
                status=TaskStatus.DONE,
                data={
                    "params": params,
                    "gen_type": gen_type,
                    "confidence": self._estimate_confidence(params),
                },
                duration_ms=duration,
            )
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _detect_type(self, prompt: str, params: dict) -> str:
        from shared.router import _detect_type
        return _detect_type(prompt, params)

    def _estimate_confidence(self, params: dict) -> float:
        """Оцениваем уверенность в парсинге (0.0-1.0)."""
        score = 0.5  # base
        if params.get("width_m") and params["width_m"] != 10:
            score += 0.1  # размеры указаны
        if params.get("length_m") and params["length_m"] != 12:
            score += 0.1
        if params.get("floors") and params["floors"] != 2:
            score += 0.1  # этажность указана
        if params.get("material") and params["material"] != "plaster":
            score += 0.1  # материал указан
        if params.get("roof_type") and params["roof_type"] != "gabled":
            score += 0.05
        if params.get("features"):
            score += 0.05
        return min(1.0, score)
