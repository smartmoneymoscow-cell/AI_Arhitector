"""
shared/agents/orchestrator.py — Оркестратор multi-agent системы.

Реально выполняет pipeline: parse → geometry → texture → render → export.
Каждый агент вызывает blender-service для выполнения bpy-скриптов.

Использование:
    from shared.agents import Orchestrator

    orch = Orchestrator(blender_service_url="http://blender-service:8082")
    result = orch.execute("двухэтажный кирпичный дом 10×12", quality="16k")
    # → {job_id, status, steps: [...], result: {...}}
"""

import os
import time
import uuid
import concurrent.futures
from typing import Optional

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus
from shared.agents.parser_agent import ParserAgent
from shared.agents.geometry_agent import GeometryAgent
from shared.agents.texture_agent import TextureAgent
from shared.agents.render_agent import RenderAgent, QUALITY_PRESETS
from shared.agents.export_agent import ExportAgent
from shared.agents.quality_agent import QualityAgent
from shared.router import route_generation
from shared.clarification import ClarificationEngine, ClarificationResult
from shared.streaming import ProgressStreamer, create_streamer


class Orchestrator:
    """
    Оркестратор multi-agent генерации.

    Полный pipeline:
        prompt → ParserAgent → route → GeometryAgent + TextureAgent → RenderAgent → ExportAgent → result

    Каждый агент реально выполняет свою задачу через blender-service.
    """

    def __init__(self, blender_service_url: str = "", output_dir: str = "/app/output"):
        self.agents: dict[str, BaseAgent] = {
            "parser": ParserAgent(),
            "geometry": GeometryAgent(),
            "texture": TextureAgent(),
            "render": RenderAgent(),
            "export": ExportAgent(),
            "quality": QualityAgent(),
        }
        self.clarification = ClarificationEngine()
        self.jobs: dict[str, dict] = {}
        self.blender_service_url = blender_service_url
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def execute(
        self,
        prompt: str,
        llm_params: dict | None = None,
        skip_clarification: bool = False,
        quality: str = "standard",
        export_formats: list[str] | None = None,
    ) -> dict:
        """
        Полный цикл генерации от промта до результата.

        Args:
            prompt: текстовый промт пользователя
            llm_params: предварительно распарсенные параметры (опционально)
            skip_clarification: пропустить уточняющие вопросы
            quality: качество рендера (preview/standard/high/ultra/16k)
            export_formats: форматы экспорта (по умолчанию ["glb"])

        Returns:
            dict с job_id, status, steps, result
        """
        job_id = uuid.uuid4().hex[:8]
        start = time.time()
        if export_formats is None:
            export_formats = ["glb"]

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
            "quality": quality,
        }
        self.jobs[job_id] = job

        try:
            # ═══ Step 1: Parse ═══
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

            streamer.emit("parse", "done", progress=15,
                          message=f"Parsed: {gen_type}, confidence={confidence:.0%}")

            # ═══ Step 1.5: Clarification ═══
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
                streamer.emit("clarification", "waiting", progress=15,
                              message="Need clarification", data=job["clarification"])
                return job

            # ═══ Step 2: Route ═══
            streamer.emit("route", "running", progress=20, message="Planning generation...")
            plan = route_generation(prompt, llm_params or params)
            building_params = plan.params.get("building", {})

            streamer.emit("route", "done", progress=25,
                          message=f"Plan: {len(plan.steps)} steps, type={gen_type}")

            # ═══ Step 3: Geometry ═══
            streamer.emit("geometry", "running", progress=30, message="Generating 3D geometry...")

            geom_params = {
                "gen_type": gen_type,
                "building_params": building_params,
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
                Task(name="geometry", agent="geometry", params=geom_params)
            )

            geometry_script = ""
            if geom_result.status == TaskStatus.DONE:
                geometry_script = geom_result.data.get("script", "")
                streamer.emit("geometry", "done", progress=45, message="Geometry generated")
            else:
                streamer.emit("geometry", "failed", progress=30,
                              message=geom_result.error or "Geometry failed")
                job["status"] = "failed"
                job["error"] = f"Geometry generation failed: {geom_result.error}"
                return job

            # ═══ Step 4: Texture ═══
            streamer.emit("texture", "running", progress=50, message="Generating PBR materials...")
            texture_result = self._run_step(
                job, "texture",
                Task(name="texture", agent="texture", params={
                    "material": params.get("material", "plaster"),
                    "resolution": 2048,
                })
            )

            texture_script = ""
            if texture_result.status == TaskStatus.DONE:
                texture_script = texture_result.data.get("script", "")
                streamer.emit("texture", "done", progress=55, message="Materials generated")

            # ═══ Step 5: Render ═══
            streamer.emit("render", "running", progress=60,
                          message=f"Rendering at {quality} quality...")

            combined_script = geometry_script
            if texture_script:
                combined_script += "\n" + texture_script

            render_output = os.path.join(self.output_dir, f"{job_id}_render.png")
            render_result = self._run_step(
                job, "render",
                Task(name="render", agent="render", params={
                    "script": combined_script,
                    "output_path": render_output,
                    "quality": quality,
                    "blender_service_url": self.blender_service_url,
                    "output_dir": self.output_dir,
                    "camera_params": self._build_camera(gen_type, params, building_params),
                })
            )

            render_path = ""
            if render_result.status == TaskStatus.DONE:
                render_path = render_result.data.get("output_path", render_output)
                streamer.emit("render", "done", progress=80,
                              message=f"Rendered: {render_result.data.get('resolution', '?')}")
            else:
                streamer.emit("render", "failed", progress=60,
                              message=render_result.error or "Render failed")

            # ═══ Step 5.5: Quality Check ═══
            if render_path:
                streamer.emit("quality", "running", progress=82,
                              message="Checking render quality...")
                quality_result = self._run_step(
                    job, "quality",
                    Task(name="quality", agent="quality", params={
                        "render_path": render_path,
                        "quality": quality,
                        "prompt": prompt,
                    })
                )
                if quality_result.status == TaskStatus.DONE:
                    qd = quality_result.data or {}
                    if not qd.get("passed", True):
                        streamer.emit("quality", "warning", progress=82,
                                      message=f"Quality check failed: {qd.get('checks', {})}")
                    else:
                        streamer.emit("quality", "done", progress=85,
                                      message="Quality check passed")

            # ═══ Step 6: Export ═══
            export_results = {}
            for fmt in export_formats:
                streamer.emit("export", "running", progress=85,
                              message=f"Exporting {fmt.upper()}...")

                export_script = combined_script if fmt in ("glb", "obj", "fbx", "usd", "ply") else ""
                export_result = self._run_step(
                    job, f"export_{fmt}",
                    Task(name="export", agent="export", params={
                        "format": fmt,
                        "script": export_script,
                        "job_id": job_id,
                        "output_dir": self.output_dir,
                        "blender_service_url": self.blender_service_url,
                        "building_params": building_params,
                    })
                )

                if export_result.status == TaskStatus.DONE:
                    export_results[fmt] = export_result.data.get("output_path", "")
                    streamer.emit("export", "done", progress=90,
                                  message=f"Exported {fmt.upper()}")
                else:
                    export_results[fmt] = None
                    streamer.emit("export", "failed", progress=85,
                                  message=f"Export {fmt} failed: {export_result.error}")

            # ═══ Final result ═══
            job["status"] = "done"
            job["result"] = {
                "gen_type": gen_type,
                "params": params,
                "building_params": building_params,
                "quality": quality,
                "render": render_path,
                "exports": export_results,
                "confidence": confidence,
            }
            streamer.emit("done", "done", progress=100, message="Generation complete!")

        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)
            streamer.emit("error", "failed", progress=0, message=str(e))

        finally:
            job["duration_ms"] = (time.time() - start) * 1000

        return job

    def _run_step(self, job: dict, step_name: str, task: Task) -> TaskResult:
        """Выполняет один шаг pipeline."""
        step_info = {
            "name": step_name,
            "agent": task.agent,
            "status": "running",
            "started_at": time.time(),
        }
        job["steps"].append(step_info)

        agent = self.agents.get(task.agent)
        if not agent:
            result = TaskResult(status=TaskStatus.FAILED, error=f"Agent '{task.agent}' not found")
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

    def _build_camera(self, gen_type: str, params: dict, building_params: dict) -> dict:
        """Строит параметры камеры в зависимости от типа генерации."""
        if gen_type == "interior":
            w = params.get("width_m", 6)
            l = params.get("length_m", 8)
            h = params.get("height_m", 3)
            return {
                "x": w / 2 - 0.5,
                "y": -l / 2 + 0.5,
                "z": h * 0.7,
                "rx": 1.047,  # 60 degrees
                "ry": 0,
                "rz": 0.785,  # 45 degrees
                "focal_length": 24,
            }
        else:
            w = building_params.get("W", 10)
            l = building_params.get("L", 12)
            floors = building_params.get("floors", 2)
            total_h = floors * building_params.get("fH", 3.0)
            return {
                "x": w * 1.5,
                "y": -l * 1.5,
                "z": total_h * 1.2,
                "rx": 1.047,
                "ry": 0,
                "rz": 0.785,
                "focal_length": 35,
            }

    def get_job(self, job_id: str) -> Optional[dict]:
        return self.jobs.get(job_id)

    def get_progress(self, job_id: str) -> dict:
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
                (s["name"] for s in job["steps"] if s["status"] == "running"), None
            ),
            "quality": job.get("quality", "standard"),
        }
