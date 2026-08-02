"""
shared/agents/orchestrator.py — Orchestrator with ISOLATED agents.

Each agent runs in a SEPARATE subprocess.
If an agent crashes → pipeline continues with fallback.
Only parser and geometry are CRITICAL (pipeline fails without them).

Circuit breaker: 5 failures → agent disabled for 60s.
"""

import logging
import os
import time
import uuid

from shared.agents.base import TaskStatus
from shared.agents.runner import AgentRunner, IsolatedResult
from shared.clarification import ClarificationEngine
from shared.router import route_generation
from shared.streaming import create_streamer

logger = logging.getLogger("archai.orchestrator")


# ═══ Pipeline profiles ═══
PIPELINE_PROFILES = {
    "quick": ["parser", "geometry", "texture", "render", "quality", "compliance", "export"],
    "standard": [
        "parser",
        "style",
        "geometry",
        "texture",
        "lighting",
        "structural",
        "compliance",
        "render",
        "quality",
        "export",
    ],
    "cad": ["parser", "style", "cad", "geometry", "texture", "lighting", "render", "quality", "compliance", "export"],
    "interactive": ["dialog", "parser", "style", "geometry", "texture", "lighting", "render", "quality", "export"],
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
        "compliance",
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
    "electrical": ["parser", "el", "compliance", "export"],
    "landscape": ["parser", "research", "landscape", "masterplan", "compliance", "export"],
    "mep_documentation": ["parser", "mep", "mep_bim", "compliance", "export"],
    "interior_full": [
        "parser",
        "concept",
        "style",
        "furniture",
        "lighting",
        "mep",
        "el",
        "structural",
        "texture",
        "render",
        "quality",
        "export",
    ],
}


class Orchestrator:
    """
    LLM-driven orchestrator with ISOLATED agent execution.

    Each agent runs in a separate subprocess.
    Non-critical agents use fallback on failure.
    Pipeline NEVER crashes due to a single agent failure.
    """

    def __init__(
        self,
        blender_service_url: str = "",
        llm_service_url: str = "",
        output_dir: str = "/app/output",
        agent_timeout: int = 120,
    ):
        self.runner = AgentRunner(default_timeout=agent_timeout)
        self.clarification = ClarificationEngine()
        self.jobs: dict[str, dict] = {}
        self.blender_service_url = blender_service_url
        self.llm_service_url = llm_service_url
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
        session_id: str = "",
    ) -> dict:
        """
        Full generation cycle with isolated agents.

        Each agent runs in subprocess → crash-safe.
        Non-critical failures → fallback → pipeline continues.
        """
        job_id = uuid.uuid4().hex[:8]
        start = time.time()
        if export_formats is None:
            export_formats = ["glb"]

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
            "fallback_agents": [],  # agents that used fallback
        }
        self.jobs[job_id] = job

        try:
            # ═══ Step 0: Dialog (multi-turn context) ═══
            dialog_enriched_prompt = prompt
            dialog_merged_params = {}
            if session_id and "dialog" in agent_sequence:
                streamer.emit("dialog", "running", progress=2, message="Analyzing conversation context...")
                dialog_result = self._run_agent(
                    "dialog",
                    {
                        "name": "dialog",
                        "agent": "dialog",
                        "params": {
                            "prompt": prompt,
                            "session_id": session_id,
                            "context": {},
                        },
                    },
                    timeout=15,
                )
                if dialog_result.status == TaskStatus.DONE and dialog_result.data:
                    dialog_data = dialog_result.data
                    if dialog_data.get("has_context"):
                        dialog_enriched_prompt = dialog_data.get("enriched_prompt", prompt)
                        dialog_merged_params = dialog_data.get("merged_params", {})
                        if dialog_data.get("is_modification"):
                            streamer.emit(
                                "dialog",
                                "done",
                                progress=5,
                                message=f"Modification detected: {dialog_data.get('modification_type', '')} {dialog_data.get('modification_target', '')}",
                            )
                        else:
                            streamer.emit("dialog", "done", progress=5, message="Context loaded")
                    else:
                        streamer.emit("dialog", "done", progress=5, message="No prior context")

            # ═══ Step 1: Parse (CRITICAL) ═══
            streamer.emit("parse", "running", progress=3, message="Parsing prompt...")
            parse_result = self._run_agent(
                "parser",
                {"name": "parse", "agent": "parser", "params": {"prompt": dialog_enriched_prompt, "use_llm": True}},
                timeout=60,
            )

            if parse_result.status == TaskStatus.FAILED:
                job["status"] = "failed"
                job["error"] = parse_result.error
                streamer.emit("parse", "failed", progress=0, message=parse_result.error)
                return job

            parsed = parse_result.data
            params = parsed.get("params", {})
            gen_type = parsed.get("gen_type", "building")
            confidence = parsed.get("confidence", 0.5)

            # Merge dialog modification params
            if dialog_merged_params:
                for k, v in dialog_merged_params.items():
                    if k.startswith("_"):
                        # Special keys like _rooms_override, _add_room
                        params[k] = v
                    elif v and not params.get(k):
                        params[k] = v

            if parse_result.fallback:
                job["fallback_agents"].append("parser")
                confidence = 0.1

            streamer.emit("parse", "done", progress=10, message=f"Parsed: {gen_type}, confidence={confidence:.0%}")

            # ═══ Step 1.5: Clarification ═══
            # ALWAYS check clarification, not just on low confidence
            clar = self.clarification.analyze(prompt, params, confidence)
            if clar.needs_clarification and not skip_clarification:
                job["status"] = "clarification_needed"
                job["clarification"] = {
                    "questions": [
                        {
                            "field": q.field,
                            "text": q.text,
                            "options": q.options,
                            "visual_options": [
                                {
                                    "id": vo.id,
                                    "title": vo.title,
                                    "description": vo.description,
                                    "pros": vo.pros,
                                    "cons": vo.cons,
                                    "image_url": vo.image_url,
                                    "recommended": vo.recommended,
                                    "price_range": vo.price_range,
                                }
                                for vo in q.visual_options
                            ],
                            "priority": q.priority,
                            "is_fork": q.is_fork,
                        }
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

            # ═══ Pre-pipeline: Intelligence agents (parallel, non-critical) ═══
            pre_agents = [
                a for a in agent_sequence if a in ("research", "market", "concept", "brand", "style", "masterplan")
            ]

            pre_pipeline_results = {}
            progress_step = 15
            progress_increment = 15 / max(len(pre_agents), 1)

            # Run pre-agents in PARALLEL (they are independent)
            if pre_agents:
                import concurrent.futures

                streamer.emit(
                    "pre_pipeline", "running", progress=15, message=f"Running {len(pre_agents)} agents in parallel..."
                )

                def _run_pre_agent(agent_name):
                    agent_params = self._build_agent_params(agent_name, params, gen_type, building_params)
                    result = self._run_agent(
                        agent_name,
                        {"name": agent_name, "agent": agent_name, "params": agent_params},
                        timeout=60,
                    )
                    return agent_name, result

                with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(pre_agents), 4)) as executor:
                    futures = {executor.submit(_run_pre_agent, a): a for a in pre_agents}
                    for future in concurrent.futures.as_completed(futures):
                        agent_name, result = future.result()
                        if result.status == TaskStatus.DONE and result.data:
                            pre_pipeline_results[agent_name] = result.data
                            if result.fallback:
                                job["fallback_agents"].append(agent_name)
                        else:
                            job["fallback_agents"].append(agent_name)
                            logger.warning("Pre-agent %s skipped: %s", agent_name, result.error)

                streamer.emit(
                    "pre_pipeline",
                    "done",
                    progress=30,
                    message=f"{len(pre_pipeline_results)}/{len(pre_agents)} agents complete",
                )

            # ═══ Step 3+4: Geometry + Texture (PARALLEL, geometry CRITICAL) ═══
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
                    "room_type": params.get("room_type", "living"),
                },
            }

            # Pass structural and MEP data to geometry agent (if available from mid-pipeline)
            # Note: mid_results is populated later, so we pass empty dict here
            # The geometry agent will generate structural/MEP if data is provided
            geom_params.setdefault("structural_calc", {})
            geom_params.setdefault("mep_calc", {})
            texture_params = {
                "material": params.get("material", "plaster"),
                "resolution": 2048,
            }

            # Run in parallel — each in its own subprocess
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                geom_future = executor.submit(
                    self._run_agent,
                    "geometry",
                    {"name": "geometry", "agent": "geometry", "params": geom_params},
                    120,
                )
                texture_future = executor.submit(
                    self._run_agent,
                    "texture",
                    {"name": "texture", "agent": "texture", "params": texture_params},
                    60,
                )
                geom_result = geom_future.result()
                texture_result = texture_future.result()

            # Geometry is CRITICAL
            if geom_result.status == TaskStatus.FAILED:
                streamer.emit("geometry", "failed", progress=35, message=geom_result.error)
                job["status"] = "failed"
                job["error"] = f"Geometry generation failed: {geom_result.error}"
                return job

            geometry_script = geom_result.data.get("script", "") if geom_result.data else ""
            if geom_result.fallback:
                job["fallback_agents"].append("geometry")
            streamer.emit(
                "geometry",
                "done",
                progress=50,
                message="Geometry generated" + (" (fallback)" if geom_result.fallback else ""),
            )

            texture_script = ""
            if texture_result.status == TaskStatus.DONE and texture_result.data:
                texture_script = texture_result.data.get("script", "")
                if texture_result.fallback:
                    job["fallback_agents"].append("texture")
            streamer.emit("texture", "done", progress=55, message="Materials generated")

            # ═══ Mid-pipeline: Non-critical agents (PARALLEL) ═══
            mid_agents = [a for a in agent_sequence if a in ("landscape", "furniture", "lighting", "mep", "structural")]
            mid_results = {}
            progress_step = 55
            progress_increment = 10 / max(len(mid_agents), 1)

            if mid_agents:
                import concurrent.futures

                streamer.emit(
                    "mid_pipeline", "running", progress=55, message=f"Running {len(mid_agents)} agents in parallel..."
                )

                def _run_mid_agent(agent_name):
                    agent_params = self._build_agent_params(agent_name, params, gen_type, building_params)
                    result = self._run_agent(
                        agent_name,
                        {"name": agent_name, "agent": agent_name, "params": agent_params},
                        timeout=60,
                    )
                    return agent_name, result

                with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(mid_agents), 4)) as executor:
                    futures = {executor.submit(_run_mid_agent, a): a for a in mid_agents}
                    for future in concurrent.futures.as_completed(futures):
                        agent_name, result = future.result()
                        if result.status == TaskStatus.DONE and result.data:
                            mid_results[agent_name] = result.data
                            if result.fallback:
                                job["fallback_agents"].append(agent_name)
                        else:
                            job["fallback_agents"].append(agent_name)

                streamer.emit(
                    "mid_pipeline", "done", progress=65, message=f"{len(mid_results)}/{len(mid_agents)} agents complete"
                )

            # ═══ Render (non-critical, uses Blender service) ═══
            streamer.emit("render", "running", progress=70, message="Rendering...")
            render_result = self._run_agent(
                "render",
                {
                    "name": "render",
                    "agent": "render",
                    "params": {
                        "geometry_script": geometry_script,
                        "texture_script": texture_script,
                        "quality": quality,
                        "output_dir": self.output_dir,
                        "job_id": job_id,
                    },
                },
                timeout=300 if quality == "16k" else 120,
            )

            render_data = {}
            if render_result.status == TaskStatus.DONE and render_result.data:
                render_data = render_result.data
                if render_result.fallback:
                    job["fallback_agents"].append("render")
            streamer.emit("render", "done", progress=85, message="Render complete")

            # ═══ Quality check (MANDATORY for 16K) ═══
            render_path = render_data.get("image_path", "") if render_data else ""
            quality_result = self._run_agent(
                "quality",
                {
                    "name": "quality",
                    "agent": "quality",
                    "params": {
                        "render_path": render_path,
                        "quality": quality,
                        "prompt": prompt,
                        "gen_type": gen_type,
                        "render_data": render_data,
                    },
                },
                timeout=60,
            )
            quality_data = quality_result.data if quality_result.status == TaskStatus.DONE else {}
            if quality_result.fallback:
                job["fallback_agents"].append("quality")

            # Quality gate: if 16K requested but not achieved — retry once
            if quality == "16k" and quality_data:
                res_check = quality_data.get("checks", {}).get("resolution", {})
                if res_check and not res_check.get("passed", True):
                    logger.warning(
                        "Quality gate: 16K requested but got %s. Retrying with higher settings.",
                        res_check.get("actual", "unknown"),
                    )
                    streamer.emit(
                        "quality",
                        "warning",
                        progress=87,
                        message=f"Quality below 16K ({res_check.get('actual', '?')}), retrying...",
                    )
                    # Retry render with forced 16K settings
                    render_result_retry = self._run_agent(
                        "render",
                        {
                            "name": "render",
                            "agent": "render",
                            "params": {
                                "geometry_script": geometry_script,
                                "texture_script": texture_script,
                                "quality": "16k_force",
                                "output_dir": self.output_dir,
                                "job_id": job_id,
                            },
                        },
                        timeout=600,
                    )
                    if render_result_retry.status == TaskStatus.DONE and render_result_retry.data:
                        render_data = render_result_retry.data
                        # Re-check quality
                        render_path = render_data.get("image_path", "") if render_data else ""
                        quality_recheck = self._run_agent(
                            "quality",
                            {
                                "name": "quality",
                                "agent": "quality",
                                "params": {
                                    "render_path": render_path,
                                    "quality": quality,
                                    "prompt": prompt,
                                },
                            },
                            timeout=60,
                        )
                        if quality_recheck.status == TaskStatus.DONE and quality_recheck.data:
                            quality_data = quality_recheck.data

            # ═══ Export (non-critical) ═══
            export_result = self._run_agent(
                "export",
                {
                    "name": "export",
                    "agent": "export",
                    "params": {
                        "geometry_script": geometry_script,
                        "export_formats": export_formats,
                        "output_dir": self.output_dir,
                        "job_id": job_id,
                    },
                },
                timeout=120,
            )
            export_data = export_result.data if export_result.status == TaskStatus.DONE else {}
            if export_result.fallback:
                job["fallback_agents"].append("export")

            # ═══ Post-pipeline: Compliance, Financial, Presentation, Drawings ═══
            post_agents = [a for a in agent_sequence if a in ("compliance", "financial", "presentation")]
            post_results = {}

            # Generate SVG drawings
            drawings = {}
            try:
                from shared.agents.drawings_svg import (
                    generate_elevation_svg,
                    generate_floor_plan_svg,
                    generate_mep_diagram_svg,
                    generate_section_svg,
                )

                drawings["floor_plan"] = generate_floor_plan_svg(params, building_params.get("rooms", []))
                drawings["section"] = generate_section_svg(params)
                drawings["elevation_front"] = generate_elevation_svg(params, "front")
                drawings["elevation_side"] = generate_elevation_svg(params, "left")
                if "mep" in mid_results:
                    drawings["mep_diagram"] = generate_mep_diagram_svg(params, mid_results.get("mep", {}))
                logger.info("SVG drawings generated: %s", list(drawings.keys()))
            except Exception as e:
                logger.warning("SVG drawings generation failed: %s", e)
            for agent_name in post_agents:
                agent_params = self._build_agent_params(agent_name, params, gen_type, building_params)
                result = self._run_agent(
                    agent_name,
                    {"name": agent_name, "agent": agent_name, "params": agent_params},
                    timeout=60,
                )
                if result.status == TaskStatus.DONE and result.data:
                    post_results[agent_name] = result.data
                if result.fallback:
                    job["fallback_agents"].append(agent_name)

            # ═══ Collect results ═══
            streamer.emit(
                "complete",
                "done",
                progress=100,
                message=f"Complete! Fallback agents: {job['fallback_agents'] or 'none'}",
            )

            agent_results = {}
            for d in [pre_pipeline_results, mid_results, post_results]:
                agent_results.update(d)

            job["status"] = "done"
            job["result"] = {
                "gen_type": gen_type,
                "params": params,
                "building_params": building_params,
                "render": render_data,
                "exports": export_data,
                "quality": quality_data,
                "confidence": confidence,
                "agent_results": agent_results,
                "drawings": drawings,
            }
            # Collect steps for API response
            job["steps"] = [
                {"name": "parse", "status": "done"},
                {"name": "route", "status": "done"},
                {"name": "geometry", "status": "done" if geometry_script else "failed"},
                {"name": "texture", "status": "done" if texture_script else "skipped"},
                {"name": "render", "status": "done" if render_data else "failed"},
                {"name": "quality", "status": "done" if quality_data else "skipped"},
                {"name": "export", "status": "done" if export_data else "skipped"},
            ]
            job["duration_ms"] = (time.time() - start) * 1000
            return job

        except Exception as e:
            logger.error("Orchestrator FATAL error for job %s: %s", job_id, e, exc_info=True)
            job["status"] = "failed"
            job["error"] = str(e)
            streamer.emit("error", "failed", progress=0, message=str(e))
            return job

    def _run_agent(self, agent_name: str, task_params: dict, timeout: int = 120) -> IsolatedResult:
        """Run agent in isolated subprocess."""
        return self.runner.run(agent_name, task_params, timeout=timeout)

    def _build_agent_params(self, agent_name: str, params: dict, gen_type: str, building_params: dict) -> dict:
        """Build parameters for specific agent, enriched with norms data."""
        base = {
            "params": params,
            "gen_type": gen_type,
            "building_params": building_params,
        }
        if agent_name in ("concept", "style"):
            base["style"] = params.get("style", "modern")
        if agent_name == "furniture":
            base["furniture"] = params.get("furniture", [])
            base["room_type"] = params.get("room_type", "living")
        if agent_name == "lighting":
            base["style"] = params.get("style", "modern")

        # ═══ Нормативные данные для ВСЕХ агентов ═══
        # Определяем применимые нормативы
        try:
            from shared.norms_reference import get_applicable_norms

            norms = get_applicable_norms(
                params.get("building_type", params.get("type", "house")),
                params.get("floors", building_params.get("floors", 2)),
                params.get("height_m", building_params.get("fH", 3.0))
                * params.get("floors", building_params.get("floors", 2)),
                params.get("material", building_params.get("mat", "brick")),
            )
            base["applicable_norms"] = norms
        except Exception:
            base["applicable_norms"] = []

        # Структурные параметры
        if agent_name in ("geometry", "structural", "compliance", "mep", "el"):
            base["structural_system"] = params.get("structural_system", "frame")
            base["foundation_type"] = params.get("foundation_type", "strip")
            base["material_concrete_class"] = params.get("material_concrete_class", "B25")
            base["steel_grade"] = params.get("steel_grade", "C345")
            base["seismic_zone"] = params.get("seismic_zone", "none")
            base["soil_type"] = params.get("soil_type", "III")
            base["fire_resistance_rating"] = params.get("fire_resistance_rating", "R45")
            base["exposure_class"] = params.get("exposure_class", "XC1")

        # Инженерные системы
        if agent_name in ("mep", "el", "compliance"):
            base["heating_type"] = params.get("heating_type", "autonomous")
            base["ventilation_type"] = params.get("ventilation_type", "natural")
            base["water_supply"] = params.get("water_supply", "central")
            base["sewage"] = params.get("sewage", "central")

        # Для structural agent — добавляем нагрузки
        if agent_name == "structural":
            base["dead_load_kN_m2"] = params.get("dead_load_kN_m2", 5.0)
            base["live_load_kN_m2"] = params.get("live_load_kN_m2", 2.0)
            base["snow_load_kN_m2"] = params.get("snow_load_kN_m2", 1.8)
            base["wind_load_kN_m2"] = params.get("wind_load_kN_m2", 0.4)
            base["total_mass_kg"] = params.get(
                "total_mass_kg",
                building_params.get("W", 10) * building_params.get("L", 12) * building_params.get("floors", 2) * 15000,
            )
            base["period_s"] = params.get("period_s", 0.5)

        # Для foundation agent
        if agent_name in ("structural", "compliance"):
            base["foundation_depth_m"] = params.get("foundation_depth_m", 1.2)
            base["pile_diameter_m"] = params.get("pile_diameter_m", 0.3)
            base["pile_length_m"] = params.get("pile_length_m", 6.0)

        return base

    def get_progress(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if not job:
            return {"error": "Job not found"}
        steps = job.get("steps", [])
        done_count = len([s for s in steps if s.get("status") == "done"])
        return {
            "job_id": job_id,
            "status": job["status"],
            "progress": int(done_count / max(len(steps), 1) * 100),
            "steps": [{"name": s.get("name", ""), "status": s.get("status", "")} for s in steps],
            "fallback_agents": job.get("fallback_agents", []),
        }
