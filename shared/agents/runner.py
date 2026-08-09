"""
shared/agents/runner.py - Выполнение агентов с fallback.

Порядок попыток:
  1. AGENT_POOL_URL задан → HTTP-вызов в agent-pool сервис (настоящая микросервисная изоляция)
  2. FORCE_SUBPROCESS=1 → multiprocessing в отдельном процессе
  3. Иначе → in-process с threading timeout

Использование:
    runner = AgentRunner(timeout=120)
    result = runner.run("geometry", task)
    if result.fallback:
        logger.debug("Agent failed, using fallback")
"""

import logging
import multiprocessing
import os
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any

import httpx

from shared.agents.base import Task, TaskStatus

logger = logging.getLogger("archai.agent_runner")


@dataclass
class IsolatedResult:
    """Результат изолированного выполнения агента."""

    status: TaskStatus
    data: Any = None
    error: str | None = None
    duration_ms: float = 0
    fallback: bool = False  # True если агент упал и использован fallback
    agent_name: str = ""


def _run_agent_in_subprocess(
    agent_class_path: str,
    task_params: dict,
    result_queue: multiprocessing.Queue,
):
    """Выполняет агента в отдельном процессе."""
    try:
        import importlib

        module_path, class_name = agent_class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        agent_cls = getattr(module, class_name)
        agent = agent_cls()

        task = Task(
            name=task_params.get("name", ""),
            agent=task_params.get("agent", ""),
            params=task_params.get("params", {}),
        )

        start = time.time()
        result = agent.process(task)
        duration = (time.time() - start) * 1000

        result_queue.put(
            {
                "status": result.status.value,
                "data": result.data,
                "error": result.error,
                "duration_ms": duration,
            }
        )

    except Exception as e:
        result_queue.put(
            {
                "status": "failed",
                "data": None,
                "error": f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()[-500:]}",
                "duration_ms": 0,
            }
        )


class AgentRunner:
    """
    Запускает агентов с fallback-поведением.

    Порядок: agent-pool HTTP → subprocess → in-process.
    """

    # Fallback данные для каждого типа агента
    FALLBACK_DATA = {
        "cad": {"step_path": None, "stl_path": None, "bpy_script": "", "note": "CAD agent skipped"},
        "dialog": {
            "enriched_prompt": "",
            "is_modification": False,
            "merged_params": {},
            "has_context": False,
            "note": "Dialog skipped",
        },
        "parser": {
            "params": {
                "object_type": "building",
                "building_type": "house",
                "floors": 2,
                "width_m": 10,
                "length_m": 12,
                "height_m": 3.0,
                "style": "modern",
                "material": "plaster",
                "roof_type": "gabled",
                "features": [],
                "furniture": [],
                "confidence": 0.1,
            },
            "gen_type": "building",
            "confidence": 0.1,
        },
        "geometry": {"script": "# Fallback: empty geometry", "type": "building"},
        "texture": {"script": "# Fallback: default materials", "resolution": 512},
        "render": {"image_path": None, "resolution": "1920x1080", "samples": 32},
        "export": {"formats": {}, "note": "Export skipped (agent failed)"},
        "quality": {"score": 0.0, "issues": ["Quality check skipped (agent failed)"], "passed": False},
        "research": {"references": [], "trends": [], "note": "Research skipped"},
        "market": {"analysis": {}, "note": "Market analysis skipped"},
        "concept": {"moodboard": [], "palette": [], "note": "Concept skipped"},
        "masterplan": {"zones": [], "note": "Masterplan skipped"},
        "landscape": {"elements": [], "note": "Landscape skipped"},
        "brand": {"style_guide": {}, "note": "Brand skipped"},
        "financial": {"cost_estimate": {}, "roi": None, "note": "Financial skipped"},
        "presentation": {"html": "", "note": "Presentation skipped"},
        "style": {"style": "modern", "note": "Style detection skipped"},
        "lighting": {"setup": "default", "note": "Lighting skipped"},
        "furniture": {"items": [], "note": "Furniture placement skipped"},
        "mep": {"systems": {}, "note": "MEP skipped"},
        "structural": {"calculation": {}, "note": "Structural skipped"},
        "compliance": {"passed": False, "issues": ["Compliance check skipped — agent unavailable"], "note": "Compliance agent failed"},
        "el": {"circuits": [], "note": "Electrical skipped"},
        "mep_bim": {"model": None, "note": "MEP BIM skipped"},
    }

    # Агенты, которые КРИТИЧНЫ - pipeline не может продолжить без них
    CRITICAL_AGENTS = {"parser", "geometry"}

    # Agent class paths for import (fallback to in-process)
    AGENT_CLASSES = {
        "parser": "shared.agents.parser_agent.ParserAgent",
        "dialog": "shared.agents.dialog_agent.DialogAgent",
        "geometry": "shared.agents.geometry_agent.GeometryAgent",
        "cad": "shared.agents.cad_agent.CADAgent",
        "texture": "shared.agents.texture_agent.TextureAgent",
        "render": "shared.agents.render_agent.RenderAgent",
        "export": "shared.agents.export_agent.ExportAgent",
        "quality": "shared.agents.quality_agent.QualityAgent",
        "research": "shared.agents.research_agent.ResearchAgent",
        "market": "shared.agents.market_agent.MarketAgent",
        "concept": "shared.agents.concept_agent.ConceptAgent",
        "masterplan": "shared.agents.masterplan_agent.MasterplanAgent",
        "landscape": "shared.agents.landscape_agent.LandscapeAgent",
        "brand": "shared.agents.brand_agent.BrandAgent",
        "financial": "shared.agents.financial_agent.FinancialAgent",
        "presentation": "shared.agents.presentation_agent.PresentationAgent",
        "style": "shared.agents.style_agent.StyleAgent",
        "lighting": "shared.agents.lighting_agent.LightingAgent",
        "furniture": "shared.agents.furniture_agent.FurnitureAgent",
        "mep": "shared.agents.mep_agent.MEPAgent",
        "structural": "shared.agents.structural_agent.StructuralAgent",
        "compliance": "shared.agents.compliance_agent.ComplianceAgent",
        "el": "shared.agents.el_agent.ELAgent",
        "mep_bim": "shared.agents.mep_bim_agent.MEPBIMAgent",
    }

    def __init__(self, default_timeout: int = 120):
        self.default_timeout = default_timeout

    def run(self, agent_name: str, task_params: dict, timeout: int | None = None) -> IsolatedResult:
        """
        Запускает агента с timeout и fallback.

        Порядок: agent-pool HTTP → subprocess → in-process.
        """
        timeout = timeout or self.default_timeout
        agent_class = self.AGENT_CLASSES.get(agent_name)

        if not agent_class:
            logger.error("Unknown agent: %s", agent_name)
            return self._fallback(agent_name, f"Unknown agent: {agent_name}")

        # Priority 1: Agent Pool microservice (real isolation via HTTP)
        agent_pool_url = os.environ.get("AGENT_POOL_URL", "")
        if agent_pool_url:
            result = self._run_via_agent_pool(agent_name, task_params, agent_pool_url, timeout)
            if result is not None:
                return result
            logger.warning("Agent pool unavailable for %s, falling back", agent_name)

        # Priority 2: Subprocess isolation
        if os.environ.get("FORCE_SUBPROCESS", "") == "1":
            try:
                return self._run_subprocess(agent_name, agent_class, task_params, timeout)
            except (OSError, PermissionError, RuntimeError) as e:
                logger.warning("Subprocess failed for %s (%s), running in-process", agent_name, e)
                return self._run_in_process(agent_name, agent_class, task_params)

        # Priority 3: In-process with threading timeout
        return self._run_in_process(agent_name, agent_class, task_params, timeout)

    def _run_via_agent_pool(
        self, agent_name: str, task_params: dict, pool_url: str, timeout: int
    ) -> IsolatedResult | None:
        """Call agent-pool microservice via HTTP. Returns None if unavailable."""
        try:
            payload = {
                "name": task_params.get("name", agent_name),
                "agent": task_params.get("agent", agent_name),
                "params": task_params.get("params", {}),
                "timeout": timeout,
            }
            with httpx.Client(timeout=float(timeout + 10)) as client:
                resp = client.post(
                    f"{pool_url}/api/v1/agents/{agent_name}/run",
                    json=payload,
                )
            if resp.status_code == 200:
                data = resp.json()
                status_str = data.get("status", "failed")
                if status_str == "done":
                    status = TaskStatus.DONE
                elif status_str == "timeout":
                    status = TaskStatus.FAILED
                else:
                    status = TaskStatus.FAILED

                return IsolatedResult(
                    status=status,
                    data=data.get("data"),
                    error=data.get("error"),
                    duration_ms=data.get("duration_ms", 0),
                    fallback=False,
                    agent_name=agent_name,
                )
            else:
                logger.warning("Agent pool returned %d for %s", resp.status_code, agent_name)
                return None
        except httpx.TimeoutException:
            logger.warning("Agent pool timeout for %s", agent_name)
            return None
        except httpx.ConnectError:
            logger.debug("Agent pool unreachable")
            return None
        except Exception as e:
            logger.warning("Agent pool call failed for %s: %s", agent_name, e)
            return None

    def _run_in_process(
        self, agent_name: str, agent_class_path: str, task_params: dict, timeout: int = 120
    ) -> IsolatedResult:
        """Fallback: run agent in current process with threading-based timeout."""
        import importlib

        result_holder: dict = {}

        def _target():
            try:
                module_path, class_name = agent_class_path.rsplit(".", 1)
                module = importlib.import_module(module_path)
                agent_cls = getattr(module, class_name)
                agent = agent_cls()

                task = Task(
                    name=task_params.get("name", ""),
                    agent=task_params.get("agent", ""),
                    params=task_params.get("params", {}),
                )

                start = time.time()
                result = agent.process(task)
                duration = (time.time() - start) * 1000
                result_holder["result"] = result
                result_holder["duration_ms"] = duration
            except Exception as e:
                result_holder["error"] = e

        start = time.time()
        worker = threading.Thread(target=_target, daemon=True)
        worker.start()
        worker.join(timeout=timeout)

        if worker.is_alive():
            logger.error("Agent %s TIMEOUT after %ds in in-process mode", agent_name, timeout)
            if agent_name in self.CRITICAL_AGENTS:
                return IsolatedResult(
                    status=TaskStatus.FAILED,
                    error=f"Agent {agent_name} timed out after {timeout}s",
                    duration_ms=(time.time() - start) * 1000,
                    fallback=False,
                    agent_name=agent_name,
                )
            return self._fallback(agent_name, f"Timeout after {timeout}s")

        duration = (time.time() - start) * 1000

        if "error" in result_holder:
            e = result_holder["error"]
            logger.error("In-process %s failed: %s", agent_name, e)
            if agent_name in self.CRITICAL_AGENTS:
                return IsolatedResult(
                    status=TaskStatus.FAILED,
                    error=str(e),
                    duration_ms=duration,
                    fallback=False,
                    agent_name=agent_name,
                )
            return self._fallback(agent_name, str(e))

        result = result_holder.get("result")
        if result is None:
            logger.error("In-process %s produced no result", agent_name)
            return self._fallback(agent_name, "Agent produced no result")

        if result.status == TaskStatus.FAILED:
            if agent_name in self.CRITICAL_AGENTS:
                return IsolatedResult(
                    status=TaskStatus.FAILED,
                    error=result.error,
                    duration_ms=duration,
                    fallback=False,
                    agent_name=agent_name,
                )
            return self._fallback(agent_name, result.error or "Agent failed")

        return IsolatedResult(
            status=result.status,
            data=result.data,
            error=result.error,
            duration_ms=duration,
            fallback=False,
            agent_name=agent_name,
        )

    def _run_subprocess(
        self, agent_name: str, agent_class_path: str, task_params: dict, timeout: int
    ) -> IsolatedResult:
        """Run agent in isolated subprocess."""
        result_queue = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=_run_agent_in_subprocess,
            args=(agent_class_path, task_params, result_queue),
            daemon=True,
        )

        start = time.time()
        process.start()

        try:
            if result_queue.empty():
                process.join(timeout=timeout)

            if process.is_alive():
                logger.error("Agent %s TIMEOUT after %ds — killing", agent_name, timeout)
                process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
                return self._fallback(agent_name, f"Timeout after {timeout}s")

            if not result_queue.empty():
                raw = result_queue.get_nowait()
                duration = (time.time() - start) * 1000

                if raw["status"] == "failed":
                    logger.warning("Agent %s FAILED: %s", agent_name, raw["error"][:200])
                    if agent_name in self.CRITICAL_AGENTS:
                        return IsolatedResult(
                            status=TaskStatus.FAILED,
                            error=raw["error"],
                            duration_ms=duration,
                            fallback=False,
                            agent_name=agent_name,
                        )
                    return self._fallback(agent_name, raw["error"])

                logger.info("Agent %s completed in %.0fms", agent_name, duration)
                return IsolatedResult(
                    status=TaskStatus(raw["status"]),
                    data=raw["data"],
                    error=raw["error"],
                    duration_ms=duration,
                    fallback=False,
                    agent_name=agent_name,
                )
            else:
                logger.error("Agent %s — no result in queue (process exited)", agent_name)
                return self._fallback(agent_name, "Process exited without result")

        except Exception as e:
            logger.error("Agent %s — runner error: %s", agent_name, e)
            process.kill()
            return self._fallback(agent_name, str(e))

    def _fallback(self, agent_name: str, error: str) -> IsolatedResult:
        """Возвращает fallback результат для агента."""
        fallback_data = self.FALLBACK_DATA.get(agent_name, {"note": f"Agent {agent_name} skipped"})

        if agent_name in self.CRITICAL_AGENTS:
            logger.error("CRITICAL agent %s failed - pipeline cannot continue: %s", agent_name, error[:200])
            return IsolatedResult(
                status=TaskStatus.FAILED,
                error=f"Critical agent {agent_name} failed: {error}",
                duration_ms=0,
                fallback=False,
                agent_name=agent_name,
            )

        logger.warning("Agent %s failed - using fallback: %s", agent_name, error[:200])
        return IsolatedResult(
            status=TaskStatus.DONE,
            data=fallback_data,
            error=error,
            duration_ms=0,
            fallback=True,
            agent_name=agent_name,
        )
