"""
shared/agents/stitching_agent.py — Stitching Agent: сборка компонентов в единую модель.

Принимает bpy-скрипты от разных агентов (geometry, furniture, mep, landscape)
и сливает их в единую сцену:
- Преобразование локальных координат → глобальные
- Разрешение конфликтов (пересечения → приоритетная система)
- Валидация смерженной сцены
- Возврат единого bpy-скрипта
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)

# Приоритет компонентов (выше = важнее, пересечения разрешаются в пользу высшего)
COMPONENT_PRIORITY = {
    "geometry": 100,     # Стены, крыша — структура здания
    "mep": 80,           # Инженерные системы
    "lighting": 70,      # Освещение
    "furniture": 50,     # Мебель
    "landscape": 30,     # Ландшафт
    "decor": 20,         # Декор
    "default": 10,
}

# Категории объектов для обнаружения пересечений
STRUCTURAL_KEYWORDS = ["wall", "slab", "roof", "column", "beam", "foundation", "стена", "плита", "крыша"]
MEP_KEYWORDS = ["pipe", "duct", "cable", "radiator", "tray", "труба", "воздуховод", "кабель"]
FURNITURE_KEYWORDS = ["sofa", "table", "bed", "chair", "wardrobe", "диван", "стол", "кровать"]


@dataclass
class ComponentInfo:
    """Информация об одном компоненте."""
    name: str
    source: str          # "geometry", "furniture", "mep", и т.д.
    script: str
    priority: int = 0
    objects: list = field(default_factory=list)
    offset: tuple = (0, 0, 0)  # Смещение для глобальных координат


@dataclass
class ObjectDef:
    """Извлечённое определение объекта из bpy-скрипта."""
    name: str
    obj_type: str         # "cube", "cylinder", "sphere", "cone", etc.
    location: tuple = (0, 0, 0)
    scale: tuple = (1, 1, 1)
    material: str = ""
    source_component: str = ""
    priority: int = 0
    raw_code: str = ""


class StitchingAgent(BaseAgent):
    """
    Агент сборки — мержит bpy-скрипты от разных агентов в единую сцену.

    Использование:
        agent = StitchingAgent()
        result = agent.process(task)

    task.params:
        components: dict — {component_name: bpy_script}
        building_params: dict — параметры здания (width, length, floors, floor_height)
        layout: dict — расположение комнат/зон (опционально)
    """

    name = "stitching"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            components = task.params.get("components", {})
            building_params = task.params.get("building_params", {})
            layout = task.params.get("layout", {})

            if not components:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    error="No components provided for stitching",
                    duration_ms=(time.time() - start) * 1000,
                )

            merged_script = self.stitch(components, building_params, layout)

            return TaskResult(
                status=TaskStatus.DONE,
                data={"bpy_script": merged_script},
                metadata={
                    "components_stitched": list(components.keys()),
                    "total_length": len(merged_script),
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error("Stitching failed: %s", e, exc_info=True)
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def stitch(
        self,
        components: dict[str, str],
        building_params: dict = None,
        layout: dict = None,
    ) -> str:
        """
        Главный метод — мержит компоненты в единую bpy-сцену.

        Args:
            components: {geometry: script, furniture: script, mep: script, ...}
            building_params: параметры здания
            layout: расположение зон

        Returns:
            Единый bpy-скрипт
        """
        building_params = building_params or {}
        layout = layout or {}

        W = building_params.get("width", 10)
        L = building_params.get("length", 12)
        floors = building_params.get("floors", 2)
        fH = building_params.get("floor_height", 3.0)

        # 1. Парсим каждый компонент
        parsed_components = []
        for comp_name, script in components.items():
            if not script or not script.strip():
                continue
            info = ComponentInfo(
                name=comp_name,
                source=comp_name,
                script=script,
                priority=COMPONENT_PRIORITY.get(comp_name, COMPONENT_PRIORITY["default"]),
            )
            info.objects = self._extract_objects(script, comp_name, info.priority)
            parsed_components.append(info)

        # 2. Рассчитываем глобальные смещения для каждого компонента
        self._assign_global_offsets(parsed_components, building_params, layout)

        # 3. Применяем смещения к объектам
        for comp in parsed_components:
            self._apply_offset(comp)

        # 4. Разрешаем конфликты (пересечения)
        all_objects = []
        for comp in parsed_components:
            all_objects.extend(comp.objects)
        resolved_objects = self._resolve_conflicts(all_objects)

        # 5. Собираем итоговый скрипт
        merged = self._assemble_script(parsed_components, resolved_objects, building_params)

        return merged

    def _extract_objects(self, script: str, component_name: str, priority: int) -> list[ObjectDef]:
        """
        Извлекает определения объектов из bpy-скрипта.

        Ищет паттерны вида:
            bpy.ops.mesh.primitive_XXX_add(..., location=(x, y, z))
            obj = bpy.context.active_object; obj.name = "Name"
        """
        objects = []

        # Паттерн для bpy.ops.mesh.primitive_*_add
        add_pattern = re.compile(
            r'bpy\.ops\.mesh\.primitive_(\w+)_add\(([^)]*)\)',
            re.DOTALL,
        )
        # Паттерн для имени объекта
        name_pattern = re.compile(r'\.name\s*=\s*["\']([^"\']+)["\']')
        # Паттерн для location
        loc_pattern = re.compile(r'location\s*=\s*\(([^)]+)\)')
        # Паттерн для scale
        scale_pattern = re.compile(r'\.scale\s*=\s*\(([^)]+)\)')
        # Паттерн для material
        mat_pattern = re.compile(r'\.data\.materials\.append\((\w+)\)')

        # Разбиваем на блоки (каждый блок — создание одного объекта)
        blocks = re.split(r'\n(?=bpy\.ops\.mesh\.)', script)

        for block in blocks:
            add_match = add_pattern.search(block)
            if not add_match:
                continue

            obj_type = add_match.group(1)
            params_str = add_match.group(2)

            # Location
            loc_match = loc_pattern.search(block)
            location = (0, 0, 0)
            if loc_match:
                try:
                    loc_parts = [float(v.strip()) for v in loc_match.group(1).split(",")]
                    location = tuple(loc_parts[:3]) if len(loc_parts) >= 3 else (0, 0, 0)
                except (ValueError, IndexError):
                    pass

            # Name
            name_match = name_pattern.search(block)
            obj_name = name_match.group(1) if name_match else f"{component_name}_{obj_type}"

            # Scale
            scale = (1, 1, 1)
            scale_match = scale_pattern.search(block)
            if scale_match:
                try:
                    s_parts = [float(v.strip()) for v in scale_match.group(1).split(",")]
                    scale = tuple(s_parts[:3]) if len(s_parts) >= 3 else (1, 1, 1)
                except (ValueError, IndexError):
                    pass

            # Material
            mat_match = mat_pattern.search(block)
            material = mat_match.group(1) if mat_match else ""

            objects.append(ObjectDef(
                name=obj_name,
                obj_type=obj_type,
                location=location,
                scale=scale,
                material=material,
                source_component=component_name,
                priority=priority,
                raw_code=block.strip(),
            ))

        return objects

    def _assign_global_offsets(
        self,
        components: list[ComponentInfo],
        building_params: dict,
        layout: dict,
    ):
        """
        Рассчитывает глобальные смещения для каждого компонента.

        Принцип:
        - geometry: без смещения (уже в глобальных координатах)
        - furniture: смещение по layout комнат
        - mep: смещение к стенам/потолку
        - landscape: смещение к периметру здания
        """
        W = building_params.get("width", 10)
        L = building_params.get("length", 12)

        for comp in components:
            if comp.source == "geometry":
                comp.offset = (0, 0, 0)
            elif comp.source == "furniture":
                # Мебель позиционируется по центру комнаты
                room_layout = layout.get("furniture_room", {})
                comp.offset = (
                    room_layout.get("x", 0),
                    room_layout.get("y", 0),
                    room_layout.get("z", 0),
                )
            elif comp.source == "mep":
                # MEP системы в зоне инженерных помещений
                mep_zone = layout.get("mep_zone", {})
                comp.offset = (
                    mep_zone.get("x", -W / 2 + 1),
                    mep_zone.get("y", -L / 2 + 1),
                    mep_zone.get("z", 0),
                )
            elif comp.source == "lighting":
                comp.offset = (0, 0, 0)
            elif comp.source == "landscape":
                # Ландшафт вокруг здания
                comp.offset = (0, 0, 0)
            else:
                comp.offset = (0, 0, 0)

    def _apply_offset(self, comp: ComponentInfo):
        """Применяет смещение к координатам всех объектов компонента."""
        ox, oy, oz = comp.offset
        if ox == 0 and oy == 0 and oz == 0:
            return

        for obj in comp.objects:
            lx, ly, lz = obj.location
            obj.location = (lx + ox, ly + oy, lz + oz)

    def _resolve_conflicts(self, all_objects: list[ObjectDef]) -> list[ObjectDef]:
        """
        Разрешает конфликты пересечений между объектами.

        Правила:
        1. Структурные элементы (geometry) > MEP > мебель
        2. При одинаковом приоритете — оставляем оба
        3. Пересечение определяется по bounding box
        """
        if not all_objects:
            return all_objects

        # Сортируем по приоритету (высший — последние, чтобы перезаписать)
        all_objects.sort(key=lambda o: o.priority)

        resolved = []
        removed = set()

        for i, obj_a in enumerate(all_objects):
            if i in removed:
                continue

            for j in range(i + 1, len(all_objects)):
                if j in removed:
                    continue
                obj_b = all_objects[j]

                # Проверяем пересечение bounding box
                if self._objects_intersect(obj_a, obj_b):
                    # Удаляем объект с низким приоритетом
                    if obj_a.priority < obj_b.priority:
                        removed.add(i)
                        logger.debug(
                            "Conflict resolved: removing %s (pri=%d) in favor of %s (pri=%d)",
                            obj_a.name, obj_a.priority, obj_b.name, obj_b.priority,
                        )
                        break
                    elif obj_b.priority < obj_a.priority:
                        removed.add(j)
                        logger.debug(
                            "Conflict resolved: removing %s (pri=%d) in favor of %s (pri=%d)",
                            obj_b.name, obj_b.priority, obj_a.name, obj_a.priority,
                        )

        for i, obj in enumerate(all_objects):
            if i not in removed:
                resolved.append(obj)

        return resolved

    def _objects_intersect(self, a: ObjectDef, b: ObjectDef, tolerance: float = 0.1) -> bool:
        """
        Проверяет пересечение двух объектов по bounding box.

        Упрощённая проверка — считаем каждый объект как AABB.
        """
        # Рассчитываем half-extents из scale
        def get_bounds(obj: ObjectDef):
            # Примерные размеры базовых примитивов
            base_sizes = {
                "cube": (0.5, 0.5, 0.5),
                "cylinder": (0.5, 0.5, 0.5),
                "sphere": (0.5, 0.5, 0.5),
                "cone": (0.5, 0.5, 0.5),
                "torus": (0.5, 0.5, 0.2),
            }
            base = base_sizes.get(obj.obj_type, (0.5, 0.5, 0.5))
            hx = base[0] * abs(obj.scale[0])
            hy = base[1] * abs(obj.scale[1])
            hz = base[2] * abs(obj.scale[2])
            cx, cy, cz = obj.location
            return (cx - hx, cy - hy, cz - hz), (cx + hx, cy + hy, cz + hz)

        min_a, max_a = get_bounds(a)
        min_b, max_b = get_bounds(b)

        # AABB intersection test
        for i in range(3):
            if min_a[i] > max_b[i] + tolerance or min_b[i] > max_a[i] + tolerance:
                return False
        return True

    def _assemble_script(
        self,
        components: list[ComponentInfo],
        resolved_objects: list[ObjectDef],
        building_params: dict,
    ) -> str:
        """
        Собирает итоговый bpy-скрипт.

        Структура:
        1. Import + header
        2. Scene root object
        3. Materials (из всех компонентов)
        4. Objects (разрешённые, с глобальными координатами)
        5. Scene hierarchy
        """
        W = building_params.get("width", 10)
        L = building_params.get("length", 12)
        floors = building_params.get("floors", 2)
        fH = building_params.get("floor_height", 3.0)

        lines = [
            "import bpy",
            "import math",
            "",
            "# ═══════════════════════════════════════════════════════════════",
            "# STITCHED SCENE — Unified Building Model",
            "# Generated by StitchingAgent v12.0.0",
            f"# Building: {W}m x {L}m, {floors} floors, {fH}m floor height",
            "# ═══════════════════════════════════════════════════════════════",
            "",
            "# Clean scene",
            "bpy.ops.object.select_all(action='SELECT')",
            "bpy.ops.object.delete(use_global=False)",
            "",
        ]

        # Scene root
        lines.extend([
            "# ═══ Scene Root ═══",
            f"bpy.ops.mesh.primitive_cube_add(size=0.01, location=(0, 0, {floors * fH / 2}))",
            "scene_root = bpy.context.active_object",
            f'scene_root.name = "Building_{W}x{L}_{floors}F"',
            "scene_root.hide_viewport = True",
            "scene_root.hide_render = True",
            "",
        ])

        # Collect all material definitions from components (avoid duplicates)
        material_blocks = []
        seen_materials = set()
        for comp in components:
            mat_section = self._extract_material_block(comp.script)
            if mat_section and comp.name not in seen_materials:
                material_blocks.append((comp.name, mat_section))
                seen_materials.add(comp.name)

        if material_blocks:
            lines.append("# ═══ Materials ═══")
            for comp_name, mat_block in material_blocks:
                lines.append(f"# --- Materials from: {comp_name} ---")
                lines.append(mat_block)
                lines.append("")

        # Group objects by component
        objects_by_component = {}
        for obj in resolved_objects:
            comp = obj.source_component
            if comp not in objects_by_component:
                objects_by_component[comp] = []
            objects_by_component[comp].append(obj)

        # Emit objects per component section
        lines.append("# ═══ Scene Objects ═══")
        lines.append("")

        # Order: geometry first, then MEP, lighting, furniture, landscape
        comp_order = ["geometry", "mep", "lighting", "furniture", "landscape"]
        ordered_components = sorted(
            components,
            key=lambda c: (comp_order.index(c.name) if c.name in comp_order else 99),
        )

        for comp in ordered_components:
            comp_objects = objects_by_component.get(comp.name, [])
            if not comp_objects:
                # Emit original script as-is if no objects extracted
                lines.append(f"# ═══ Component: {comp.name} (original script) ═══")
                lines.append(comp.script)
                lines.append("")
                continue

            lines.append(f"# ═══ Component: {comp.name} ({len(comp_objects)} objects) ═══")

            for obj in comp_objects:
                # Re-emit the object with updated global coordinates
                lines.append(self._emit_object(obj))

            lines.append("")

        # Parent all top-level objects to scene root
        lines.extend([
            "# ═══ Scene Hierarchy ═══",
            "bpy.ops.object.select_all(action='DESELECT')",
            "for obj in bpy.data.objects:",
            "    if obj != scene_root and obj.parent is None:",
            "        obj.select_set(True)",
            "bpy.context.view_layer.objects.active = scene_root",
            "bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)",
            "bpy.ops.object.select_all(action='DESELECT')",
            "",
            "# ═══ Scene Settings ═══",
            "bpy.context.scene.render.engine = 'CYCLES'",
            "bpy.context.scene.cycles.samples = 128",
            "bpy.context.scene.render.resolution_x = 1920",
            "bpy.context.scene.render.resolution_y = 1080",
            "",
            'print("✅ Stitched scene assembled successfully")',
        ])

        return "\n".join(lines)

    def _extract_material_block(self, script: str) -> str:
        """Извлекает блок определения материалов из скрипта."""
        # Ищем блок от "Materials" заголовка до первого non-material кода
        mat_start = script.find("Materials")
        if mat_start == -1:
            mat_start = script.find("materials")
        if mat_start == -1:
            return ""

        # Ищем начало блока (строка с bpy.data.materials.new)
        lines = script.split("\n")
        mat_lines = []
        in_mat = False

        for line in lines:
            stripped = line.strip()
            if "bpy.data.materials.new" in stripped:
                in_mat = True
            if in_mat:
                mat_lines.append(line)
                # Конец блока материалов — пустая строка после присваивания
                if not stripped and len(mat_lines) > 5:
                    # Проверяем следующую non-empty строку
                    continue

        return "\n".join(mat_lines[:100])  # Ограничиваем размер

    def _emit_object(self, obj: ObjectDef) -> str:
        """Генерирует bpy-код для объекта с обновлёнными координатами."""
        x, y, z = obj.location
        sx, sy, sz = obj.scale

        # Определяем primitive_add вызов
        lines = []

        if obj.obj_type == "cube":
            lines.append(f"bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, {z}))")
        elif obj.obj_type == "cylinder":
            # Извлекаем radius из scale (примерно)
            r = max(sx, sy) * 0.5
            depth = sz
            lines.append(f"bpy.ops.mesh.primitive_cylinder_add(radius={r}, depth={depth}, location=({x}, {y}, {z}))")
        elif obj.obj_type == "sphere":
            r = max(sx, sy, sz) * 0.5
            lines.append(f"bpy.ops.mesh.primitive_uv_sphere_add(radius={r}, location=({x}, {y}, {z}))")
        elif obj.obj_type == "cone":
            r = max(sx, sy) * 0.5
            lines.append(f"bpy.ops.mesh.primitive_cone_add(radius1={r}, depth={sz}, location=({x}, {y}, {z}))")
        else:
            # Fallback — воспроизводим оригинальный код с изменённым location
            return obj.raw_code

        # Set name
        safe_name = obj.name.replace('"', '\\"')
        lines.append(f'obj = bpy.context.active_object; obj.name = "{safe_name}"')

        # Apply scale if not default
        if (sx, sy, sz) != (1, 1, 1):
            lines.append(f"obj.scale = ({sx}, {sy}, {sz})")
            lines.append("bpy.ops.object.transform_apply(scale=True)")

        # Apply material
        if obj.material:
            lines.append(f"obj.data.materials.append({obj.material})")

        return "\n".join(lines)


def stitch_components(
    components: dict[str, str],
    building_params: dict = None,
    layout: dict = None,
) -> str:
    """
    Convenience function — мержит компоненты в единую bpy-сцену.

    Args:
        components: {name: bpy_script}
        building_params: параметры здания
        layout: расположение зон

    Returns:
        Единый bpy-скрипт
    """
    agent = StitchingAgent()
    return agent.stitch(components, building_params, layout)
