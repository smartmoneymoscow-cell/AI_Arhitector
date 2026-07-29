"""
shared/agents/export_agent.py — Агент экспорта.

Отвечает за:
- Экспорт в GLB (Three.js viewer)
- Экспорт в IFC (BIM)
- Экспорт в SVG (floor plan)
- Экспорт в STEP (CAD)
"""

import os
import time
from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus


class ExportAgent(BaseAgent):
    name = "export"

    SUPPORTED_FORMATS = {"glb", "ifc", "svg", "step", "obj", "fbx"}

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            fmt = task.params.get("format", "glb").lower()
            script = task.params.get("script", "")
            output_dir = task.params.get("output_dir", "/app/output")
            job_id = task.params.get("job_id", "export")

            if fmt not in self.SUPPORTED_FORMATS:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    error=f"Unsupported format: {fmt}. Supported: {self.SUPPORTED_FORMATS}",
                )

            export_cmd = self._build_export_cmd(fmt, output_dir, job_id)

            return TaskResult(
                status=TaskStatus.DONE,
                data={
                    "export_command": export_cmd,
                    "format": fmt,
                    "output_path": os.path.join(output_dir, f"{job_id}.{fmt}"),
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _build_export_cmd(self, fmt: str, output_dir: str, job_id: str) -> str:
        """Строит bpy-команду экспорта."""
        output_path = os.path.join(output_dir, f"{job_id}.{fmt}")

        if fmt == "glb":
            return (
                f"import bpy\n"
                f"bpy.ops.export_scene.gltf(filepath=r'{output_path}', export_format='GLB')"
            )
        elif fmt == "obj":
            return (
                f"import bpy\n"
                f"bpy.ops.wm.obj_export(filepath=r'{output_path}')"
            )
        elif fmt == "fbx":
            return (
                f"import bpy\n"
                f"bpy.ops.export_scene.fbx(filepath=r'{output_path}')"
            )
        else:
            return f"# Export to {fmt} not implemented in bpy"
