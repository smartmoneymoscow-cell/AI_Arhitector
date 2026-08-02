"""
shared/agents/cad_agent.py — CAD generation agent.

Generates parametric walls with window/door openings using OCCT.
Falls back to bpy-script boolean operations if OCCT unavailable.

This agent runs in the orchestrator pipeline alongside geometry agent.
Geometry agent handles bpy scripts; CAD agent handles precise CAD models.
"""

import logging
import time
import uuid

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger("archai.cad_agent")


class CADAgent(BaseAgent):
    """
    Generates precise CAD models with parametric walls and openings.

    Uses OpenCascade for boolean operations (wall - openings).
    Falls back to Blender boolean modifier if OCCT unavailable.

    Output:
        - STEP file (for engineering)
        - STL file (for mesh processing)
        - GLB file (for Three.js viewer, via trimesh if available)
        - bpy script (fallback for Blender rendering)
    """

    name = "cad"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params.get("params", {})
            building_params = task.params.get("building_params", {})
            gen_type = task.params.get("gen_type", "building")

            if gen_type == "interior":
                return self._process_interior(params, building_params, start)

            return self._process_building(params, building_params, start)

        except Exception as e:
            logger.error("CAD agent failed: %s", e, exc_info=True)
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _process_building(self, params: dict, building_params: dict, start: float) -> TaskResult:
        """Generate building CAD model."""
        from shared.cad_builder import BuildingBuilder

        builder = BuildingBuilder()
        result = builder.generate(params, building_params)

        # Also generate bpy script for rendering
        bpy_script = ""
        try:
            from shared.cad_builder import generate_building_from_params_bpy
            bpy_script = generate_building_from_params_bpy(params, building_params)
        except Exception as e:
            logger.warning("bpy script generation failed: %s", e)

        return TaskResult(
            status=TaskStatus.DONE,
            data={
                "step_path": result.get("step_path"),
                "stl_path": result.get("stl_path"),
                "analysis": result.get("analysis"),
                "occt_available": result.get("occt_available", False),
                "bpy_script": bpy_script,
                "spec": result.get("spec"),
            },
            duration_ms=(time.time() - start) * 1000,
        )

    def _process_interior(self, params: dict, building_params: dict, start: float) -> TaskResult:
        """Interior CAD is handled by geometry agent — pass through."""
        return TaskResult(
            status=TaskStatus.DONE,
            data={
                "note": "Interior CAD handled by geometry agent",
                "bpy_script": "",
            },
            duration_ms=(time.time() - start) * 1000,
        )
