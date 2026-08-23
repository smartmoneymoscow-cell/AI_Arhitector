"""
shared/agents/parser_agent.py — LLM-only парсинг промтов.
Regex fallback УДАЛЁН. При недоступности LLM → AllModelsFailedError.

v10.3 — LLM Service proxy: if llm_service_url is set, use HTTP proxy
instead of calling OpenRouter/Gemini directly (avoids missing API keys on Gateway).
"""

import logging
import time

import httpx

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus
from shared.parser import AllModelsFailedError, parse_prompt

logger = logging.getLogger("archai.parser_agent")


def _parse_via_llm_service(llm_service_url: str, prompt: str) -> dict:
    """Parse via LLM Service HTTP proxy (avoids needing API keys on Gateway)."""
    resp = httpx.post(
        f"{llm_service_url}/api/v1/parse",
        json={"text": prompt},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


class ParserAgent(BaseAgent):
    name = "parser"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            prompt = task.params.get("prompt", "")
            llm_service_url = task.params.get("llm_service_url", "")

            # v10.3: prefer LLM Service proxy over direct API calls
            if llm_service_url:
                logger.info("Parsing via LLM Service: %s", llm_service_url)
                params = _parse_via_llm_service(llm_service_url, prompt)
            else:
                params = parse_prompt(prompt)

            gen_type = "interior" if params.get("object_type") in ("interior", "room") else "building"

            # ═══ Compute confidence from parsed data quality ═══
            llm_confidence = params.get("confidence")
            if llm_confidence is not None and isinstance(llm_confidence, (int, float)):
                confidence = float(llm_confidence)
            else:
                # Auto-compute: more populated fields → higher confidence
                score = 0.0
                obj_type = params.get("object_type", "")
                if obj_type and obj_type not in ("building", "house"):
                    score += 0.25  # specific object_type (interior, landscape, etc.)
                elif obj_type:
                    score += 0.15  # generic but present
                if params.get("building_type"):
                    score += 0.2
                if params.get("room_type"):
                    score += 0.15
                if params.get("floors"):
                    score += 0.1
                if params.get("width_m") and params.get("length_m"):
                    score += 0.1
                if params.get("material"):
                    score += 0.1
                if params.get("style"):
                    score += 0.05
                if params.get("features"):
                    score += 0.05
                confidence = min(max(score, 0.5), 0.95)  # at least 0.5 if LLM returned data

            return TaskResult(
                status=TaskStatus.DONE,
                data={"params": params, "gen_type": gen_type, "confidence": confidence},
                duration_ms=(time.time() - start) * 1000,
            )
        except AllModelsFailedError as e:
            return TaskResult(
                status=TaskStatus.FAILED, error=f"LLM unavailable: {e}", duration_ms=(time.time() - start) * 1000
            )
        except Exception as e:
            return TaskResult(status=TaskStatus.FAILED, error=str(e), duration_ms=(time.time() - start) * 1000)
