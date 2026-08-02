"""
shared/agents/export_agent.py — Агент экспорта.

Реально выполняет экспорт через blender-service.
Поддерживает: GLB, IFC, SVG, OBJ, FBX.
"""

import os
import time
import uuid

import httpx

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

# Команды экспорта для разных форматов
EXPORT_COMMANDS = {
    "glb": lambda path: (
        f"""
import bpy
bpy.ops.export_scene.gltf(filepath=r'{path}', export_format='GLB', use_selection=False,
    export_apply=True, export_materials='EXPORT')
"""
    ),
    "obj": lambda path: (
        f"""
import bpy
bpy.ops.wm.obj_export(filepath=r'{path}', export_materials=True, export_triangulated_mesh=True)
"""
    ),
    "fbx": lambda path: (
        f"""
import bpy
bpy.ops.export_scene.fbx(filepath=r'{path}', use_selection=False, apply_unit_scale=True,
    apply_scale_options='FBX_SCALE_ALL', mesh_smooth_type='FACE')
"""
    ),
    "usd": lambda path: (
        f"""
import bpy
bpy.ops.wm.usd_export(filepath=r'{path}', export_materials=True, export_meshes=True)
"""
    ),
    "ply": lambda path: (
        f"""
import bpy
bpy.ops.export_mesh.ply(filepath=r'{path}')
"""
    ),
}


class ExportAgent(BaseAgent):
    """Агент экспорта — вызывает blender-service для реального экспорта."""

    name = "export"

    SUPPORTED_FORMATS = set(EXPORT_COMMANDS.keys()) | {"ifc", "svg"}

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            fmt = task.params.get("format", "glb").lower()
            script = task.params.get("script", "")
            output_dir = task.params.get("output_dir", "/app/output")
            job_id = task.params.get("job_id", uuid.uuid4().hex[:8])
            blender_service_url = task.params.get("blender_service_url", "")

            if fmt not in self.SUPPORTED_FORMATS:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    error=f"Unsupported format: {fmt}. Supported: {self.SUPPORTED_FORMATS}",
                    duration_ms=(time.time() - start) * 1000,
                )

            output_path = os.path.join(output_dir, f"{job_id}.{fmt}")
            os.makedirs(output_dir, exist_ok=True)

            if fmt == "ifc":
                return self._export_ifc(task.params, output_path, start)
            elif fmt == "svg":
                return self._export_svg(task.params, output_path, start)

            # bpy-based export
            export_cmd = EXPORT_COMMANDS[fmt](output_path)
            full_script = script + "\n" + export_cmd

            if blender_service_url:
                result = self._call_blender_service(blender_service_url, full_script, output_path)
            else:
                result = self._run_local(full_script, output_path, job_id)

            return TaskResult(
                status=TaskStatus.DONE,
                data={
                    "output_path": output_path,
                    "format": fmt,
                    "job_id": job_id,
                    **result,
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _export_ifc(self, params: dict, output_path: str, start: float) -> TaskResult:
        """Экспорт через IfcOpenShell (без Blender)."""
        try:
            from shared.ifc_generator import generate_ifc_building

            building_params = params.get("building_params", {})
            generate_ifc_building(building_params, output_path)
            return TaskResult(
                status=TaskStatus.DONE,
                data={"output_path": output_path, "format": "ifc"},
                duration_ms=(time.time() - start) * 1000,
            )
        except ImportError:
            return TaskResult(
                status=TaskStatus.FAILED,
                error="ifcopenshell not installed",
                duration_ms=(time.time() - start) * 1000,
            )

    def _export_svg(self, params: dict, output_path: str, start: float) -> TaskResult:
        """Экспорт SVG плана этажа (без Blender)."""
        try:
            from shared.floorplan import generate_floorplan_svg

            building_params = params.get("building_params", {})
            floor = params.get("floor", 1)
            svg = generate_floorplan_svg(building_params, floor)
            with open(output_path, "w") as f:
                f.write(svg)
            return TaskResult(
                status=TaskStatus.DONE,
                data={"output_path": output_path, "format": "svg"},
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=f"SVG export failed: {e}",
                duration_ms=(time.time() - start) * 1000,
            )

    def _call_blender_service(self, base_url: str, script: str, output_path: str) -> dict:
        """Вызывает blender-service через HTTP."""
        try:
            with httpx.Client(timeout=300.0) as client:
                r = client.post(
                    f"{base_url}/api/v1/execute",
                    json={"script": script, "output_path": output_path},
                )
                if r.status_code == 200:
                    return r.json()
                raise RuntimeError(f"Blender service returned {r.status_code}: {r.text[:500]}")
        except httpx.TimeoutException:
            raise TimeoutError("Blender service export timeout")
        except Exception as e:
            raise RuntimeError(f"Blender service call failed: {e}")

    def _run_local(self, script: str, output_path: str, job_id: str) -> dict:
        """Локальный запуск Blender для экспорта."""
        import subprocess

        from shared.config import settings

        script_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_export.py")

        try:
            compile(script, f"<{job_id}_export>", "exec")
        except SyntaxError as e:
            raise ValueError(f"Export script syntax error: {e}")

        with open(script_path, "w") as f:
            f.write(script)

        try:
            result = subprocess.run(
                [
                    settings.BLENDER_PATH,
                    "--background",
                    "--factory-startup",
                    "--log-level",
                    "0",
                    "--python",
                    script_path,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Blender export failed: {result.stderr[-500:]}")
            return {"blender_output": result.stdout[-200:]}
        except subprocess.TimeoutExpired:
            raise TimeoutError("Blender export timeout (120s)")
        finally:
            if os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except OSError:
                    pass
