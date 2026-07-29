"""
shared/agents/render_agent.py — Агент рендеринга.

Отвечает за:
- Рендер через Blender (EEVEE preview / Cycles final)
- Multi-camera рендер
- Управление качеством (resolution, samples)
"""

import time
from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus


class RenderAgent(BaseAgent):
    name = "render"

    # Presets для разного качества
    QUALITY_PRESETS = {
        "preview": {
            "engine": "BLENDER_EEVEE",
            "resolution_x": 1280,
            "resolution_y": 720,
            "samples": 64,
        },
        "standard": {
            "engine": "BLENDER_EEVEE",
            "resolution_x": 1920,
            "resolution_y": 1080,
            "samples": 128,
        },
        "high": {
            "engine": "BLENDER_EEVEE",
            "resolution_x": 3840,
            "resolution_y": 2160,
            "samples": 256,
        },
        "ultra": {
            "engine": "CYCLES",
            "resolution_x": 3840,
            "resolution_y": 2160,
            "samples": 1024,
        },
    }

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            script = task.params.get("script", "")
            quality = task.params.get("quality", "standard")
            output_path = task.params.get("output_path", "")

            preset = self.QUALITY_PRESETS.get(quality, self.QUALITY_PRESETS["standard"])

            render_cmd = self._build_render_cmd(preset, output_path)

            return TaskResult(
                status=TaskStatus.DONE,
                data={
                    "render_command": render_cmd,
                    "preset": preset,
                    "quality": quality,
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _build_render_cmd(self, preset: dict, output_path: str) -> str:
        """Строит bpy-команду рендера."""
        lines = [
            "import bpy",
            f"bpy.context.scene.render.engine = '{preset['engine']}'",
            f"bpy.context.scene.render.resolution_x = {preset['resolution_x']}",
            f"bpy.context.scene.render.resolution_y = {preset['resolution_y']}",
        ]

        if preset["engine"] == "CYCLES":
            lines.append(f"bpy.context.scene.cycles.samples = {preset['samples']}")
            lines.append("bpy.context.scene.cycles.use_denoising = True")
        else:
            lines.append(f"bpy.context.scene.eevee.taa_render_samples = {preset['samples']}")

        if output_path:
            lines.append(f"bpy.context.scene.render.filepath = r'{output_path}'")
            lines.append("bpy.ops.render.render(write_still=True)")

        return "\n".join(lines)
