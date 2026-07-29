"""
shared/agents/orchestrator.py — Оркестратор multi-agent системы.

Центральный координатор:
- Принимает промт
- Декомпозирует на задачи
- Диспетчеризирует по агентам (параллельно где возможно)
- Собирает результаты
- Обрабатывает ошибки (retry, fallback)

Использование:
    from shared.agents import Orchestrator

    orch = Orchestrator()
    result = orch.execute("двухэтажный кирпичный дом 10×12")
    # → {job_id, status, steps: [...], result: {...}}
"""

import time
import uuid
import concurrent.futures
from typing import Optional

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus
from shared.agents.parser_agent import ParserAgent
from shared.agents.geometry_agent import GeometryAgent
from shared.agents.texture_agent import TextureAgent
from shared.agents.render_agent import RenderAgent
from shared.agents.export_agent import ExportAgent
from shared.router import route_generation


class Orchestrator:
    """
    Оркестратор multi-agent генерации.

    Flow:
        prompt → ParserAgent → route_generation → [GeometryAgent, TextureAgent, ...] → result
    """

    def __init__(self):
        self.agents: dict[str, BaseAgent] = {
            "parser": ParserAgent(),
            "geometry": GeometryAgent(),
            "texture": TextureAgent(),
            "render": RenderAgent(),
            "export": ExportAgent(),
        }
        self.jobs: dict[str, dict] = {}

    def execute(self, prompt: str, llm_params: dict | None = None) -> dict:
        """
        Полный цикл генерации от промта до результата.

        Args:
            prompt: текстовый промт пользователя
            llm_params: предварительно распарсенные параметры (опционально)

        Returns:
            dict с job_id, status, steps, result
        """
        job_id = uuid.uuid4().hex[:8]
        start = time.time()

        job = {
            "job_id": job_id,
            "prompt": prompt,
            "status": "running",
            "steps": [],
            "result": None,
            "error": None,
            "started_at": start,
        }
        self.jobs[job_id] = job

        try:
            # Step1: Parse
            parse_result = self._run_step(
                job, "parse",
                Task(name="parse", agent="parser", params={"prompt": prompt, "use_llm": True})
            )

            if parse_result.status == TaskStatus.FAILED:
                job["status"] = "failed"
                job["error"] = parse_result.error
                return job

            parsed = parse_result.data
            params = parsed["params"]
            gen_type = parsed["gen_type"]

            # Step2: Route (determines full plan)
            plan = route_generation(prompt, llm_params)

            # Step3: Geometry generation
            geometry_params = {
                "gen_type": gen_type,
                "building_params": plan.params.get("building", {}),
                "interior_params": {
                    "width": params.get("width_m", 6),
                    "length": params.get("length_m", 8),
                    "height": params.get("height_m", 3),
                    "style": params.get("style", "modern"),
                    "furniture": params.get("furniture", []),
                },
            }

            geom_result = self._run_step(
                job, "geometry",
                Task(name="geometry", agent="geometry", params=geometry_params)
            )

            # Step4: Texture application
            texture_result = self._run_step(
                job, "texture",
                Task(name="texture", agent="texture", params={
                    "material": params.get("material", "plaster"),
                    "resolution": 2048,
                })
            )

            # Step5: Export
            export_result = self._run_step(
                job, "export_glb",
                Task(name="export", agent="export", params={
                    "format": "glb",
                    "job_id": job_id,
                })
            )

            # Compile result
            job["status"] = "done"
            job["result"] = {
                "gen_type": gen_type,
                "params": params,
                "building_params": plan.params.get("building", {}),
                "geometry": geom_result.data if geom_result.status == TaskStatus.DONE else None,
                "texture": texture_result.data if texture_result.status == TaskStatus.DONE else None,
                "export": export_result.data if export_result.status == TaskStatus.DONE else None,
                "confidence": parsed.get("confidence", 0.5),
            }

        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)

        finally:
            job["duration_ms"] = (time.time() - start) * 1000

        return job

    def _run_step(self, job: dict, step_name: str, task: Task) -> TaskResult:
        """Выполняет один шаг и записывает результат в job."""
        step_info = {
            "name": step_name,
            "agent": task.agent,
            "status": "running",
            "started_at": time.time(),
        }
        job["steps"].append(step_info)

        agent = self.agents.get(task.agent)
        if not agent:
            result = TaskResult(
                status=TaskStatus.FAILED,
                error=f"Agent '{task.agent}' not found",
            )
            step_info["status"] = "failed"
            step_info["error"] = result.error
            return result

        try:
            task.start()
            result = agent.process(task)
            task.complete(result)

            step_info["status"] = result.status.value
            step_info["duration_ms"] = result.duration_ms
            if result.error:
                step_info["error"] = result.error

            return result

        except Exception as e:
            task.fail(str(e))
            step_info["status"] = "failed"
            step_info["error"] = str(e)
            return TaskResult(status=TaskStatus.FAILED, error=str(e))

    def get_job(self, job_id: str) -> Optional[dict]:
        """Получить статус задачи по ID."""
        return self.jobs.get(job_id)

    def get_progress(self, job_id: str) -> dict:
        """Получить прогресс задачи."""
        job = self.jobs.get(job_id)
        if not job:
            return {"error": "Job not found"}

        total = len(job["steps"])
        done = sum(1 for s in job["steps"] if s["status"] in ("done", "skipped"))
        failed = sum(1 for s in job["steps"] if s["status"] == "failed")

        return {
            "job_id": job_id,
            "status": job["status"],
            "total_steps": total,
            "completed": done,
            "failed": failed,
            "progress": int(done / max(total, 1) * 100),
            "current_step": next(
                (s["name"] for s in job["steps"] if s["status"] == "running"),
                None
            ),
        }
