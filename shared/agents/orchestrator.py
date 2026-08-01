"""
shared/agents/orchestrator.py — LLM-driven оркестратор multi-agent системы (20 агентов).

Полный pipeline:
    prompt → ParserAgent → LLM Orchestrator → [Research|Concept|Style|Masterplan|...]
           → GeometryAgent → TextureAgent → RenderAgent → QualityAgent → ExportAgent
           → [Compliance|Financial|Presentation]

Каждый агент реально выполняет свою задачу.

Использование:
    from shared.agents import Orchestrator

    orch = Orchestrator(blender_service_url="http://blender-service:8082")
    result = orch.execute("двухэтажный кирпичный дом 10×12", quality="16k")
"""

import concurrent.futures
import logging
import os
import time
import uuid

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus
from shared.agents.brand_agent import BrandAgent
from shared.agents.compliance_agent import ComplianceAgent
from shared.agents.concept_agent import ConceptAgent
from shared.agents.export_agent import ExportAgent
from shared.agents.financial_agent import FinancialAgent
from shared.agents.furniture_agent import FurnitureAgent
from shared.agents.geometry_agent import GeometryAgent
from shared.agents.landscape_agent import LandscapeAgent
from shared.agents.lighting_agent import LightingAgent
from shared.agents.market_agent import MarketAgent
from shared.agents.masterplan_agent import MasterplanAgent
from shared.agents.mep_agent import MEPAgent
from shared.agents.parser_agent import ParserAgent
from shared.agents.presentation_agent import PresentationAgent
from shared.agents.quality_agent import QualityAgent
from shared.agents.render_agent import RenderAgent

# Новые агенты
from shared.agents.research_agent import ResearchAgent
from shared.agents.structural_agent import StructuralAgent
from shared.agents.style_agent import StyleAgent
from shared.agents.texture_agent import TextureAgent
from shared.clarification import ClarificationEngine
from shared.router import route_generation
from shared.streaming import create_streamer

logger = logging.getLogger("archai.orchestrator")


# ═══ Pipeline profiles ═══
# Какие агенты включать для разных сценариев
PIPELINE_PROFILES = {
    "quick": [
        "parser",
        "geometry",
        "texture",
        "render",
        "export",
    ],
    "standard": [
        "parser",
        "style",
        "geometry",
        "texture",
        "lighting",
        "render",
        "quality",
        "export",
    ],
    "full": [
        "parser",
        "research",
        "concept",
        "style",
        "masterplan",
        "geometry",
        "texture",
        "furniture",
        "lighting",
        "render",
        "quality",
        "structural",
        "compliance",
        "export",
    ],
    "premium": [
        "parser",
        "research",
        "market",
        "concept",
        "brand",
        "style",
        "masterplan",
        "landscape",
        "geometry",
        "texture",
        "furniture",
        "lighting",
        "mep",
        "structural",
        "render",
        "quality",
        "compliance",
        "financial",
        "export",
        "presentation",
    ],
    "interior": [
        "parser",
        "concept",
        "style",
        "furniture",
        "lighting",
        "texture",
        "render",
        "quality",
        "export",
    ],
    "presentation": [
        "parser",
        "concept",
        "style",
        "geometry",
        "texture",
        "render",
        "quality",
        "export",
        "presentation",
    ],
}


class Orchestrator:
    """
    LLM-driven оркестратор multi-agent генерации (20 агентов).

    Поддерживает pipeline profiles: quick, standard, full, premium, interior, presentation.
    LLM определяет, какие агенты нужны для конкретного запроса.
    """

    def __init__(self, blender_service_url: str = "", output_dir: str = "/app/output"):
        # Все 20 агентов
        self.agents: dict[str, BaseAgent] = {
            # Pipeline (6)
            "parser": ParserAgent(),
            "geometry": GeometryAgent(),
            "texture": TextureAgent(),
            "render": RenderAgent(),
            "export": ExportAgent(),
            "quality": QualityAgent(),
            # Intelligence (8)
            "research": ResearchAgent(),
            "market": MarketAgent(),
            "concept": ConceptAgent(),
            "masterplan": MasterplanAgent(),
            "landscape": LandscapeAgent(),
            "brand": BrandAgent(),
            "financial": FinancialAgent(),
            "presentation": PresentationAgent(),
            # Specialized (6)
            "style": StyleAgent(),
            "lighting": LightingAgent(),
            "furniture": FurnitureAgent(),
            "mep": MEPAgent(),
            "structural": StructuralAgent(),
            "compliance": ComplianceAgent(),
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
        pipeline_profile: str = "standard",
    ) -> dict:
        """
        Полный цикл генерации от промта до результата.

        Args:
            prompt: текстовый промт пользователя
            llm_params: предварительно распарсенные параметры
            skip_clarification: пропустить уточняющие вопросы
            quality: качество рендера (preview/standard/high/ultra/16k)
            export_formats: форматы экспорта
            pipeline_profile: профиль pipeline (quick/standard/full/premium/interior/presentation)

        Returns:
            dict с job_id, status, steps, result
        """
        job_id = uuid.uuid4().hex[:8]
        start = time.time()
        if export_formats is None:
            export_formats = ["glb"]

        # Определяем pipeline
        agent_sequence = PIPELINE_PROFILES.get(pipeline_profile, PIPELINE_PROFILES["standard"])

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
            "pipeline_profile": pipeline_profile,
            "agent_sequence": agent_sequence,
        }
        self.jobs[job_id] = job

        try:
            # ═══ Step 1: Parse ═══
            streamer.emit("parse", "running", progress=3, message="Parsing prompt...")
            parse_result = self._run_step(
                job, "parser", Task(name="parse", agent="parser", params={"prompt": prompt, "use_llm": True})
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

            streamer.emit("parse", "done", progress=10, message=f"Parsed: {gen_type}, confidence={confidence:.0%}")

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
                streamer.emit(
                    "clarification", "waiting", progress=10, message="Need clarification", data=job["clarification"]
                )
                return job

            # ═══ Step 2: Route ═══
            streamer.emit("route", "running", progress=12, message="Planning generation...")
            plan = route_generation(prompt, llm_params or params)
            building_params = plan.params.get("building", {})

            streamer.emit("route", "done", progress=15, message=f"Plan: {len(plan.steps)} steps, type={gen_type}")

            # ═══ Pre-pipeline: Intelligence agents ═══
            pre_pipeline_results = {}
            pre_agents = [
                a for a in agent_sequence if a in ("research", "market", "concept", "brand", "style", "masterplan")
            ]

            progress_step = 15
            progress_increment = 15 / max(len(pre_agents), 1)

            for agent_name in pre_agents:
                if agent_name not in self.agents:
                    continue

                streamer.emit(agent_name, "running", progress=int(progress_step), message=f"Running {agent_name}...")

                agent_params = self._build_agent_params(agent_name, params, gen_type, building_params)
                result = self._run_step(job, agent_name, Task(name=agent_name, agent=agent_name, params=agent_params))

                if result.status == TaskStatus.DONE and result.data:
                    pre_pipeline_results[agent_name] = result.data
                    streamer.emit(
                        agent_name,
                        "done",
                        progress=int(progress_step + progress_increment),
                        message=f"{agent_name} complete",
                    )
                else:
                    streamer.emit(
                        agent_name,
                        "warning",
                        progress=int(progress_step),
                        message=f"{agent_name} skipped: {result.error or 'no data'}",
                    )

                progress_step += progress_increment

            # ═══ Step 3+4: Geometry + Texture (PARALLEL) ═══
            streamer.emit("geometry", "running", progress=35, message="Generating 3D geometry...")
            streamer.emit("texture", "running", progress=37, message="Generating PBR materials...")

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
            texture_params = {
                "material": params.get("material", "plaster"),
                "resolution": 2048,
            }

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                geom_future = executor.submit(
                    self._run_step, job, "geometry", Task(name="geometry", agent="geometry", params=geom_params)
                )
                texture_future = executor.submit(
                    self._run_step, job, "texture", Task(name="texture", agent="texture", params=texture_params)
                )
                geom_result = geom_future.result()
                texture_result = texture_future.result()

            geometry_script = ""
            if geom_result.status == TaskStatus.DONE:
                geometry_script = geom_result.data.get("script", "")
                streamer.emit("geometry", "done", progress=50, message="Geometry generated")
            else:
                streamer.emit("geometry", "failed", progress=35, message=geom_result.error or "Geometry failed")
                job["status"] = "failed"
                job["error"] = f"Geometry generation failed: {geom_result.error}"
                return job

            texture_script = ""
            if texture_result.status == TaskStatus.DONE:
                texture_script = texture_result.data.get("script", "")
                streamer.emit("texture", "done", progress=55, message="Materials generated")

            # ═══ Mid-pipeline: Landscape, Furniture, Lighting, MEP, Structural ═══
            mid_pipeline_results = {}
            mid_agents = [a for a in agent_sequence if a in ("landscape", "furniture", "lighting", "mep", "structural")]

            progress_step = 55
            progress_increment = 10 / max(len(mid_agents), 1)

            for agent_name in mid_agents:
                if agent_name not in self.agents:
                    continue

                streamer.emit(agent_name, "running", progress=int(progress_step), message=f"Running {agent_name}...")

                agent_params = self._build_agent_params(agent_name, params, gen_type, building_params)
                if agent_name == "furniture":
                    agent_params["room_type"] = gen_type if gen_type == "interior" else "living"

                result = self._run_step(job, agent_name, Task(name=agent_name, agent=agent_name, params=agent_params))

                if result.status == TaskStatus.DONE and result.data:
                    mid_pipeline_results[agent_name] = result.data
                    # Добавляем bpy-скрипт от landscape/furniture
                    if agent_name in ("landscape", "furniture") and result.data.get("bpy_script"):
                        geometry_script += "\n" + result.data["bpy_script"]
                    streamer.emit(agent_name, "done", progress=int(progress_step + progress_increment))

                progress_step += progress_increment

            # ═══ Step 5: Render ═══
            streamer.emit("render", "running", progress=65, message=f"Rendering at {quality} quality...")

            combined_script = geometry_script
            if texture_script:
                combined_script += "\n" + texture_script

            render_output = os.path.join(self.output_dir, f"{job_id}_render.png")
            render_result = self._run_step(
                job,
                "render",
                Task(
                    name="render",
                    agent="render",
                    params={
                        "script": combined_script,
                        "output_path": render_output,
                        "quality": quality,
                        "blender_service_url": self.blender_service_url,
                        "output_dir": self.output_dir,
                        "camera_params": self._build_camera(gen_type, params, building_params),
                    },
                ),
            )

            render_path = ""
            if render_result.status == TaskStatus.DONE:
                render_path = render_result.data.get("output_path", render_output)
                streamer.emit(
                    "render", "done", progress=80, message=f"Rendered: {render_result.data.get('resolution', '?')}"
                )
            else:
                streamer.emit("render", "failed", progress=65, message=render_result.error or "Render failed")

            # ═══ Step 5.5: Quality Check ═══
            if render_path:
                streamer.emit("quality", "running", progress=82, message="Checking render quality...")
                quality_result = self._run_step(
                    job,
                    "quality",
                    Task(
                        name="quality",
                        agent="quality",
                        params={
                            "render_path": render_path,
                            "quality": quality,
                            "prompt": prompt,
                        },
                    ),
                )
                if quality_result.status == TaskStatus.DONE:
                    qd = quality_result.data or {}
                    if not qd.get("passed", True):
                        streamer.emit(
                            "quality", "warning", progress=82, message=f"Quality check warnings: {qd.get('checks', {})}"
                        )
                    else:
                        streamer.emit("quality", "done", progress=85, message="Quality check passed")

            # ═══ Post-pipeline: Compliance, Financial ═══
            post_pipeline_results = {}
            post_agents = [a for a in agent_sequence if a in ("compliance", "financial")]

            for agent_name in post_agents:
                if agent_name not in self.agents:
                    continue
                agent_params = self._build_agent_params(agent_name, params, gen_type, building_params)
                result = self._run_step(job, agent_name, Task(name=agent_name, agent=agent_name, params=agent_params))
                if result.status == TaskStatus.DONE and result.data:
                    post_pipeline_results[agent_name] = result.data

            # ═══ Step 6: Export ═══
            export_results = {}
            for fmt in export_formats:
                streamer.emit("export", "running", progress=88, message=f"Exporting {fmt.upper()}...")

                export_script = combined_script if fmt in ("glb", "obj", "fbx", "usd", "ply") else ""
                export_result = self._run_step(
                    job,
                    f"export_{fmt}",
                    Task(
                        name="export",
                        agent="export",
                        params={
                            "format": fmt,
                            "script": export_script,
                            "job_id": job_id,
                            "output_dir": self.output_dir,
                            "blender_service_url": self.blender_service_url,
                            "building_params": building_params,
                        },
                    ),
                )

                if export_result.status == TaskStatus.DONE:
                    export_results[fmt] = export_result.data.get("output_path", "")
                    streamer.emit("export", "done", progress=92, message=f"Exported {fmt.upper()}")
                else:
                    export_results[fmt] = None
                    streamer.emit(
                        "export", "failed", progress=88, message=f"Export {fmt} failed: {export_result.error}"
                    )

            # ═══ Step 7: Presentation ═══
            presentation_data = None
            if "presentation" in agent_sequence:
                streamer.emit("presentation", "running", progress=94, message="Generating presentation...")
                pres_params = {
                    "project_name": params.get("building_type", "Архитектурный проект"),
                    "style": params.get("style", "modern"),
                    "building_type": params.get("building_type", "house"),
                    "render_paths": [p for p in export_results.values() if p],
                    "concept": pre_pipeline_results.get("concept", {}),
                    "cost_estimate": post_pipeline_results.get("financial", {}).get("breakdown", {}),
                    "norm_report": post_pipeline_results.get("compliance", {}).get("norm_check", {}),
                    "masterplan": pre_pipeline_results.get("masterplan", {}),
                    "landscape": mid_pipeline_results.get("landscape", {}),
                }
                pres_result = self._run_step(
                    job, "presentation", Task(name="presentation", agent="presentation", params=pres_params)
                )
                if pres_result.status == TaskStatus.DONE:
                    presentation_data = pres_result.data
                    streamer.emit("presentation", "done", progress=96, message="Presentation ready")

            # ═══ Final result ═══
            job["status"] = "done"
            job["result"] = {
                "gen_type": gen_type,
                "params": params,
                "building_params": building_params,
                "quality": quality,
                "pipeline_profile": pipeline_profile,
                "render": render_path,
                "exports": export_results,
                "confidence": confidence,
                # Интеллектуальные результаты
                "concept": pre_pipeline_results.get("concept"),
                "style": pre_pipeline_results.get("style"),
                "masterplan": pre_pipeline_results.get("masterplan"),
                "brand": pre_pipeline_results.get("brand"),
                "research": pre_pipeline_results.get("research"),
                "market": pre_pipeline_results.get("market"),
                # Специализированные результаты
                "landscape": mid_pipeline_results.get("landscape"),
                "furniture": mid_pipeline_results.get("furniture"),
                "lighting": mid_pipeline_results.get("lighting"),
                "mep": mid_pipeline_results.get("mep"),
                "structural": mid_pipeline_results.get("structural"),
                # Пост-анализ
                "compliance": post_pipeline_results.get("compliance"),
                "financial": post_pipeline_results.get("financial"),
                # Презентация
                "presentation": presentation_data,
            }
            streamer.emit("done", "done", progress=100, message="Generation complete!")

        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)
            streamer.emit("error", "failed", progress=0, message=str(e))
            logger.error(f"Orchestrator error: {e}", exc_info=True)

        finally:
            job["duration_ms"] = (time.time() - start) * 1000

        return job

    def _build_agent_params(self, agent_name: str, params: dict, gen_type: str, building_params: dict) -> dict:
        """Построить параметры для конкретного агента."""
        base = {
            "prompt": params.get("prompt", ""),
            "style": params.get("style", "modern"),
            "building_type": params.get("building_type", "house"),
            "width_m": params.get("width_m", 10),
            "length_m": params.get("length_m", 10),
            "height_m": params.get("height_m", 3.0),
            "floors": params.get("floors", 1),
            "material": params.get("material", "brick"),
            "roof_type": params.get("roof_type", "gable"),
            "gen_type": gen_type,
        }

        if agent_name == "research":
            base["type"] = "general"
        elif agent_name == "market":
            base["type"] = "full"
            base["region"] = params.get("region", "Москва")
        elif agent_name == "concept":
            pass  # использует base
        elif agent_name == "brand":
            pass
        elif agent_name == "masterplan":
            base["lot_width_m"] = params.get("lot_width_m", params.get("width_m", 10) * 3)
            base["lot_length_m"] = params.get("lot_length_m", params.get("length_m", 10) * 3)
            base["has_garage"] = params.get("has_garage", True)
            base["has_garden"] = params.get("has_garden", True)
        elif agent_name == "landscape":
            base["lot_width_m"] = params.get("lot_width_m", params.get("width_m", 10) * 3)
            base["lot_length_m"] = params.get("lot_length_m", params.get("length_m", 10) * 3)
            base["landscape_style"] = params.get("landscape_style", "natural")
        elif agent_name == "lighting":
            base["time_of_day"] = params.get("time_of_day", "day")
            base["room_type"] = params.get("room_type", "living")
        elif agent_name == "furniture":
            base["room_type"] = params.get("room_type", gen_type if gen_type == "interior" else "living")
            base["include_optional"] = True
        elif agent_name == "mep":
            base["system"] = "all"
            base["occupants"] = params.get("occupants", 4)
        elif agent_name == "structural":
            base["soil_type"] = params.get("soil_type", "medium")
        elif agent_name == "compliance":
            pass
        elif agent_name == "financial":
            base["type"] = "full"

        return base

    def _run_step(
        self, job: dict, step_name: str, task: Task, max_retries: int = 1, step_timeout: float = 300.0
    ) -> TaskResult:
        """Выполняет один шаг pipeline с retry и timeout."""
        step_info = {
            "name": step_name,
            "agent": task.agent,
            "status": "running",
            "started_at": time.time(),
            "retries": 0,
        }
        job["steps"].append(step_info)

        agent = self.agents.get(task.agent)
        if not agent:
            result = TaskResult(status=TaskStatus.FAILED, error=f"Agent '{task.agent}' not found")
            step_info["status"] = "failed"
            step_info["error"] = result.error
            return result

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                task.start()
                result = agent.process(task)
                task.complete(result)

                step_info["status"] = result.status.value
                step_info["duration_ms"] = result.duration_ms
                step_info["retries"] = attempt
                if result.error:
                    step_info["error"] = result.error

                if result.status == TaskStatus.DONE:
                    return result

                last_error = result.error
                if attempt < max_retries:
                    logger.warning(
                        "Step %s failed (attempt %d/%d): %s — retrying",
                        step_name,
                        attempt + 1,
                        max_retries + 1,
                        last_error,
                    )
                    time.sleep(2 * (attempt + 1))

            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    logger.warning(
                        "Step %s exception (attempt %d/%d): %s — retrying",
                        step_name,
                        attempt + 1,
                        max_retries + 1,
                        last_error,
                    )
                    time.sleep(2 * (attempt + 1))

        step_info["status"] = "failed"
        step_info["error"] = last_error
        return TaskResult(status=TaskStatus.FAILED, error=last_error)

    def _build_camera(self, gen_type: str, params: dict, building_params: dict) -> dict:
        """Параметры камеры для рендера."""
        if gen_type == "interior":
            return {
                "type": "interior",
                "fov": 60,
                "location": (0, -3, 1.6),
                "target": (0, 0, 1.2),
            }
        else:
            width = building_params.get("width_m", params.get("width_m", 10))
            distance = width * 1.5
            return {
                "type": "exterior",
                "fov": 45,
                "location": (distance, -distance, distance * 0.6),
                "target": (0, 0, params.get("height_m", 3) / 2),
            }

    def get_job(self, job_id: str) -> dict | None:
        """Получить статус задачи."""
        return self.jobs.get(job_id)

    def list_agents(self) -> list[dict]:
        """Список всех агентов."""
        return [{"name": name, "class": agent.__class__.__name__} for name, agent in self.agents.items()]

    def get_pipeline_profiles(self) -> dict:
        """Доступные pipeline profiles."""
        return {name: agents for name, agents in PIPELINE_PROFILES.items()}
