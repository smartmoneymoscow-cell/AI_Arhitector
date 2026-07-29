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
from shared.clarification import ClarificationEngine, ClarificationResult
from shared.streaming import ProgressStreamer, create_streamer


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
        self.clarification = ClarificationEngine()
        self.jobs: dict[str, dict] = {}

    def execute(self, prompt: str, llm_params: dict | None = None, skip_clarification: bool = False) -> dict:
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

        # Create streamer for SSE progress
        streamer = create_streamer(job_id)

        job = {
            "job_id": job_id,
            "prompt": prompt,
            "status": "running",
            "steps": [],
            "result": None,
            "error": None,
            "started_at": start,
            "streamer": streamer,
        }
        self.jobs[job_id] = job

        try:
            # Step1: Parse
            streamer.emit("parse", "running", progress=5, message="Parsing prompt...")
            parse_result = self._run_step(
                job, "parse",
                Task(name="parse", agent="parser", params={"prompt": prompt, "use_llm": True})
            )

            if parse_result.status == TaskStatus.FAILED:
                job["status"] = "failed"
                job["error"] = parse_result.error
                streamer.emit("parse", "failed", progress=0, message=parse_result.error)
                return job

            parsed = parse_result.data
            params = parsed["params"]
            gen_type = parsed["gen_type"]
            confidence = parsed.get("confidence", 0.5)

            streamer.emit("parse", "done", progress=20,
                          message=f"Parsed: {gen_type}, confidence={confidence:.0%}")

            # Step1.5: Check if clarification needed
            clar = self.clarification.analyze(prompt, params, confidence)
            if clar.needs_clarification and not skip_clarification:
                job["status"] = "clarification_needed"
                job["clarification"] = {
                    "questions": [
                        {"field": q.field, "text": q.text, "options": q.options, "priority": q.priority}
                        for q in clar.questions
                    ],
                    "partial_params": params,
                    "confidence": confidence,
                }
                streamer.emit("clarification", "waiting", progress=20,
                              message="Need clarification", data=job["clarification"])
                return job

            # Step2: Route (determines full plan)
            streamer.emit("route", "running", progress=25, message="Planning generation...")
            plan = route_generation(prompt, llm_params)

            # Step3: Geometry generation
            streamer.emit("route", "done", progress=30, message=f"Plan: {len(plan.steps)} steps")
            streamer.emit("geometry", "running", progress=35, message="Generating3D geometry...")

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

            if geom_result.status == TaskStatus.DONE:
                streamer.emit("geometry", "done", progress=60, message="Geometry generated")
            else:
                streamer.emit("geometry", "failed", progress=35, message=geom_result.error or "Geometry failed")

            # Step4: Texture application
            streamer.emit("texture", "running", progress=65, message="Applying textures...")
            texture_result = self._run_step(
                job, "texture",
                Task(name="texture", agent="texture", params={
                    "material": params.get("material", "plaster"),
                    "resolution": 2048,
                })
            )
            streamer.emit("texture", "done", progress=75, message="Textures applied")

            # Step5: Export
            streamer.emit("export", "running", progress=80, message="Exporting GLB...")
            export_result = self._run_step(
                job, "export_glb",
                Task(name="export", agent="export", params={
                    "format": "glb",
                    "job_id": job_id,
                })
            )
            streamer.emit("export", "done", progress=95, message="Export complete")

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
            streamer.emit("done", "done", progress=100, message="Generation complete!")

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
