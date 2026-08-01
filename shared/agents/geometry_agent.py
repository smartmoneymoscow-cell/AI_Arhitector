"""
shared/agents/geometry_agent.py — Агент генерации3D геометрии.

Отвечает за:
- Генерацию bpy-скриптов для зданий и интерьеров
- Декомпозицию на подзадачи (стены, крыша, окна, балкон)
- Контроль качества геометрии
"""

import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus


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

        return TaskResult(
            status=TaskStatus.DONE,
            data={"script": script, "type": "building"},
            duration_ms=(time.time() - start) * 1000,
        )

    def _generate_interior(self, task: Task, start: float) -> TaskResult:
        from shared.blender import generate_interior_script

        interior_params = task.params.get("interior_params", task.params)
        script = generate_interior_script(interior_params)

        return TaskResult(
            status=TaskStatus.DONE,
            data={"script": script, "type": "interior"},
            duration_ms=(time.time() - start) * 1000,
        )
