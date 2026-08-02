"""
shared/agents/parser_agent.py — LLM-only парсинг промтов.
Regex fallback УДАЛЁН. При недоступности LLM → AllModelsFailedError.
"""

import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus
from shared.parser import AllModelsFailedError, parse_prompt


class ParserAgent(BaseAgent):
    name = "parser"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            prompt = task.params.get("prompt", "")
            params = parse_prompt(prompt)
            gen_type = "interior" if params.get("object_type") in ("interior", "room") else "building"
            return TaskResult(
                status=TaskStatus.DONE,
                data={"params": params, "gen_type": gen_type, "confidence": params.get("confidence", 0.5)},
                duration_ms=(time.time() - start) * 1000,
            )
        except AllModelsFailedError as e:
            return TaskResult(
                status=TaskStatus.FAILED, error=f"LLM unavailable: {e}", duration_ms=(time.time() - start) * 1000
            )
        except Exception as e:
            return TaskResult(status=TaskStatus.FAILED, error=str(e), duration_ms=(time.time() - start) * 1000)
