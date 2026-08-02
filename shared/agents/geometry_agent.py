"""
shared/agents/geometry_agent.py — Агент генерации3D геометрии.

Отвечает за:
- Генерацию bpy-скриптов для зданий и интерьеров
- Декомпозицию на подзадачи (стены, крыша, окна, балкон)
- Контроль качества геометрии
"""

import logging
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class GeometryAgent(BaseAgent):
    name = "geometry"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            gen_type = task.params.get("gen_type", "building")

            if gen_type == "interior":
                return self._generate_interior(task, start)
            else:
                return self._generate_building(task, start)

        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def decompose(self, task: Task) -> list[Task]:
        """Разбивает генерацию здания на параллельные подзадачи."""
        gen_type = task.params.get("gen_type", "building")
        if gen_type == "interior":
            return [task]  # интерьер не декомпозируется

        building_params = task.params.get("building_params", {})
        subtasks = []

        # Стены + окна (каждый этаж отдельно)
        for fl in range(building_params.get("floors", 2)):
            subtasks.append(
                Task(
                    name=f"walls_floor_{fl}",
                    agent="geometry",
                    params={**building_params, "gen_type": "building", "floor": fl, "part": "walls"},
                    parent_id=task.id,
                )
            )

        # Крыша
        subtasks.append(
            Task(
                name="roof",
                agent="geometry",
                params={**building_params, "gen_type": "building", "part": "roof"},
                parent_id=task.id,
            )
        )

        # Балкон (если есть)
        if building_params.get("balcony"):
            subtasks.append(
                Task(
                    name="balcony",
                    agent="geometry",
                    params={**building_params, "gen_type": "building", "part": "balcony"},
                    parent_id=task.id,
                )
            )

        # Ландшафт
        subtasks.append(
            Task(
                name="landscape",
                agent="geometry",
                params={**building_params, "gen_type": "building", "part": "landscape"},
                parent_id=task.id,
            )
        )

        return subtasks

    def _generate_building(self, task: Task, start: float) -> TaskResult:
        from shared.blender import generate_bpy_script

        building_params = task.params.get("building_params", task.params)
        script = generate_bpy_script(building_params)

        # Add structural frame if available
        structural_calc = task.params.get("structural_calc")
        if structural_calc:
            try:
                from shared.agents.structural_bpy import generate_structural_bpy
                struct_script = generate_structural_bpy(building_params, structural_calc)
                script += "\n" + struct_script
            except Exception as e:
                logger.warning(f"Structural bpy failed: {e}")

        # Add MEP systems if available
        mep_calc = task.params.get("mep_calc")
        if mep_calc:
            try:
                from shared.agents.mep_bpy import generate_mep_bpy
                mep_script = generate_mep_bpy(building_params, mep_calc)
                script += "\n" + mep_script
            except Exception as e:
                logger.warning(f"MEP bpy failed: {e}")

        return TaskResult(
            status=TaskStatus.DONE,
            data={"script": script, "type": "building"},
            duration_ms=(time.time() - start) * 1000,
        )

    def _generate_interior(self, task: Task, start: float) -> TaskResult:
        from shared.blender import generate_interior_script

        interior_params = task.params.get("interior_params", task.params)
        script = generate_interior_script(interior_params)

        # Add high-quality furniture if available
        furniture_list = interior_params.get("furniture", [])
        room_type = interior_params.get("room_type", "living")
        style = interior_params.get("style", "modern")
        if furniture_list:
            try:
                from shared.agents.furniture_bpy import generate_furniture_bpy
                furn_script = generate_furniture_bpy(
                    room_type, furniture_list,
                    interior_params.get("width", 6),
                    interior_params.get("length", 8),
                    style
                )
                script += "\n" + furn_script
            except Exception as e:
                logger.warning(f"Furniture bpy failed: {e}")

        return TaskResult(
            status=TaskStatus.DONE,
            data={"script": script, "type": "interior"},
            duration_ms=(time.time() - start) * 1000,
        )
