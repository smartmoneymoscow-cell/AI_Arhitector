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
        params = task.params.get("params", {})
        script = generate_bpy_script(building_params)

        # ═══ Добавляем конструктивные элементы по нормативам ═══
        structural_system = params.get("structural_system", task.params.get("structural_system", "frame"))
        material = params.get("material", building_params.get("mat", "brick"))
        floors = building_params.get("floors", 2)
        W = building_params.get("W", 10)
        L = building_params.get("L", 12)
        fH = building_params.get("fH", 3.0)

        script += self._generate_structural_elements(
            structural_system, material, floors, W, L, fH, params
        )

        # Добавляем фундамент по нормативам
        foundation_type = params.get("foundation_type", task.params.get("foundation_type", "strip"))
        script += self._generate_foundation(foundation_type, W, L, floors, params)

        # Добавляем огнезащиту если нужно
        fire_rating = params.get("fire_resistance_rating", task.params.get("fire_resistance_rating", "R45"))
        script += self._generate_fire_protection(material, fire_rating, floors)

        # Add structural frame if available from structural agent
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

    def _generate_structural_elements(self, system: str, material: str,
                                       floors: int, W: float, L: float, fH: float,
                                       params: dict) -> str:
        """Генерация конструктивных элементов по СП 63/16/15/64."""
        lines = ["\n# ═══ STRUCTURAL ELEMENTS (per SP 63/16/15/64) ═══"]
        lines.append("import bpy")
        lines.append("import bmesh")
        lines.append("from mathutils import Vector")

        concrete_class = params.get("material_concrete_class", "B25")
        steel_grade = params.get("steel_grade", "C345")

        if material in ("concrete", "reinforced_concrete", "бетон"):
            # ЖБ каркас — колонны и ригели по СП 63
            col_size = 0.4 if floors <= 5 else 0.6  # размер колонны
            beam_h = 0.5 if floors <= 5 else 0.7    # высота ригеля
            beam_w = 0.3 if floors <= 5 else 0.4    # ширина ригеля

            lines.append(f"\n# ЖБ каркас: {concrete_class}, колонны {col_size}м, ригели {beam_h}м")
            lines.append(f"col_w = {col_size}")
            lines.append(f"beam_h = {beam_h}")
            lines.append(f"beam_w = {beam_w}")

            # Сетка колонн (СП 63 — шаг 6-9м типично)
            col_spacing_x = min(6.0, W / max(2, int(W / 6)))
            col_spacing_y = min(6.0, L / max(2, int(L / 6)))

            lines.append(f"col_sx = {col_spacing_x:.2f}")
            lines.append(f"col_sy = {col_spacing_y:.2f}")

            # Генерация колонн
            lines.append("""
# Колоны ЖБ каркаса (СП 63.13330)
n_cols_x = int(W / col_sx) + 1
n_cols_y = int(L / col_sy) + 1
for i in range(n_cols_x):
    for j in range(n_cols_y):
        x = i * col_sx
        y = j * col_sy
        if x > W + 0.01 or y > L + 0.01:
            continue
        for fl in range(floors):
            z = fl * fH
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x + col_w/2, y + col_w/2, z + fH/2))
            col = bpy.context.active_object
            col.name = f'Column_{fl}_{i}_{j}'
            col.scale = (col_w, col_w, fH)
            mat = bpy.data.materials.get('concrete_structural')
            if not mat:
                mat = bpy.data.materials.new('concrete_structural')
                mat.diffuse_color = (0.5, 0.55, 0.55, 1)
            col.data.materials.append(mat)
""")

            # Ригели между колоннами
            lines.append("""
# Ригели ЖБ каркаса (СП 63.13330)
for fl in range(floors):
    z = fl * fH + fH
    # Ригели по X
    for j in range(n_cols_y):
        y = j * col_sy + col_w / 2
        for i in range(n_cols_x - 1):
            x1 = i * col_sx + col_w
            x2 = (i + 1) * col_sx
            if x2 <= x1:
                continue
            mid_x = (x1 + x2) / 2
            bpy.ops.mesh.primitive_cube_add(size=1, location=(mid_x, y, z))
            beam = bpy.context.active_object
            beam.name = f'BeamX_{fl}_{i}_{j}'
            beam.scale = (x2 - x1, beam_w, beam_h)
            beam.data.materials.append(mat)
    # Ригели по Y
    for i in range(n_cols_x):
        x = i * col_sx + col_w / 2
        for j in range(n_cols_y - 1):
            y1 = j * col_sy + col_w
            y2 = (j + 1) * col_sy
            if y2 <= y1:
                continue
            mid_y = (y1 + y2) / 2
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x, mid_y, z))
            beam = bpy.context.active_object
            beam.name = f'BeamY_{fl}_{i}_{j}'
            beam.scale = (beam_w, y2 - y1, beam_h)
            beam.data.materials.append(mat)
""")

        elif material in ("steel", "сталь"):
            # Стальной каркас по СП 16
            lines.append(f"\n# Стальной каркас: {steel_grade}")
            lines.append("""
# Колоны стального каркаса (двутавры)
col_spacing = 6.0
mat_steel = bpy.data.materials.get('steel_structural')
if not mat_steel:
    mat_steel = bpy.data.materials.new('steel_structural')
    mat_steel.diffuse_color = (0.4, 0.42, 0.45, 1)
    mat_steel.metallic = 0.8
    mat_steel.roughness = 0.3

for i in range(int(W / col_spacing) + 1):
    for j in range(int(L / col_spacing) + 1):
        x = i * col_spacing
        y = j * col_spacing
        if x > W + 0.01 or y > L + 0.01:
            continue
        for fl in range(floors):
            z = fl * fH
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z + fH/2))
            col = bpy.context.active_object
            col.name = f'SteelCol_{fl}_{i}_{j}'
            col.scale = (0.3, 0.3, fH)
            col.data.materials.append(mat_steel)
""")

        elif material in ("wood", "дерево"):
            # Деревянный каркас по СП 64
            lines.append("\n# Деревянный каркас (СП 64.13330)")
            lines.append("""
mat_wood = bpy.data.materials.get('wood_structural')
if not mat_wood:
    mat_wood = bpy.data.materials.new('wood_structural')
    mat_wood.diffuse_color = (0.45, 0.3, 0.15, 1)
""")

        return "\n".join(lines)

    def _generate_foundation(self, ftype: str, W: float, L: float,
                              floors: int, params: dict) -> str:
        """Генерация фундамента по СП 22/24."""
        lines = ["\n# ═══ FOUNDATION (per SP 22.13330 / SP 24.13330) ═══"]

        if ftype == "strip":
            # Ленточный фундамент
            depth = params.get("foundation_depth_m", 1.2)
            width = 0.6 if floors <= 3 else 0.8
            lines.append(f"\n# Ленточный фундамент (СП 22): глубина {depth}м, ширина {width}м")
            lines.append("""
fnd_depth = {depth}
fnd_w = {width}
mat_fnd = bpy.data.materials.get('foundation')
if not mat_fnd:
    mat_fnd = bpy.data.materials.new('foundation')
    mat_fnd.diffuse_color = (0.35, 0.35, 0.3, 1)
# Лента по периметру
for side in [(W/2, -fnd_w/2, W/2, L+fnd_w/2),
             (W/2, L+fnd_w/2, W+fnd_w/2, L+fnd_w/2),
             (W+fnd_w/2, -fnd_w/2, W+fnd_w/2, L+fnd_w/2),
             (W/2, -fnd_w/2, W+fnd_w/2, -fnd_w/2)]:
    pass  # Generated by blender script
bpy.ops.mesh.primitive_cube_add(size=1, location=(W/2, L/2, -fnd_depth/2))
fnd = bpy.context.active_object
fnd.name = 'Foundation'
fnd.scale = (W+fnd_w*2, L+fnd_w*2, fnd_depth)
fnd.data.materials.append(mat_fnd)
""".format(depth=depth, width=width)]

        elif ftype == "slab":
            # Плитный фундамент
            lines.append("\n# Плитный фундамент (СП 22)")
            lines.append("""
bpy.ops.mesh.primitive_cube_add(size=1, location=(W/2, L/2, -0.3))
fnd = bpy.context.active_object
fnd.name = 'FoundationSlab'
fnd.scale = (W+1, L+1, 0.4)
mat_fnd = bpy.data.materials.get('foundation')
if not mat_fnd:
    mat_fnd = bpy.data.materials.new('foundation')
    mat_fnd.diffuse_color = (0.35, 0.35, 0.3, 1)
fnd.data.materials.append(mat_fnd)
""")

        elif ftype == "pile":
            # Свайное поле (СП 24)
            pile_d = params.get("pile_diameter_m", 0.3)
            min_spacing = 3.5 * pile_d
            lines.append(f"\n# Свайное поле (СП 24): ∅{pile_d}м, шаг {min_spacing:.2f}м")
            lines.append("""
pile_d = {pile_d}
pile_spacing = {spacing}
n_piles_x = max(2, int(W / pile_spacing) + 1)
n_piles_y = max(2, int(L / pile_spacing) + 1)
mat_pile = bpy.data.materials.get('pile')
if not mat_pile:
    mat_pile = bpy.data.materials.new('pile')
    mat_pile.diffuse_color = (0.3, 0.3, 0.3, 1)
for i in range(n_piles_x):
    for j in range(n_piles_y):
        x = (i + 0.5) * W / n_piles_x
        y = (j + 0.5) * L / n_piles_y
        bpy.ops.mesh.primitive_cylinder_add(radius=pile_d/2, depth=8,
            location=(x, y, -4))
        pile = bpy.context.active_object
        pile.name = f'Pile_{i}_{j}'
        pile.data.materials.append(mat_pile)
# Ростверк
bpy.ops.mesh.primitive_cube_add(size=1, location=(W/2, L/2, -0.15))
cap = bpy.context.active_object
cap.name = 'PileCap'
cap.scale = (W+0.6, L+0.6, 0.3)
cap.data.materials.append(mat_pile)
""".format(pile_d=pile_d, spacing=min_spacing))

        return "\n".join(lines)

    def _generate_fire_protection(self, material: str, rating: str, floors: int) -> str:
        """Генерация огнезащиты по СП 2.13130."""
        lines = ["\n# ═══ FIRE PROTECTION (per SP 2.13130) ═══"]

        if material in ("steel", "сталь") and floors > 1:
            lines.append("\n# Огнезащита стальных конструкций")
            lines.append("""
# Покрытие огнезащитным составом (индикативно)
for obj in bpy.data.objects:
    if 'SteelCol' in obj.name or 'SteelBeam' in obj.name:
        mod = obj.modifiers.new('FireProtect', 'SOLIDIFY')
        mod.thickness = 0.02
        mod.offset = 1
""")

        return "\n".join(lines)

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
                    room_type, furniture_list, interior_params.get("width", 6), interior_params.get("length", 8), style
                )
                script += "\n" + furn_script
            except Exception as e:
                logger.warning(f"Furniture bpy failed: {e}")

        return TaskResult(
            status=TaskStatus.DONE,
            data={"script": script, "type": "interior"},
            duration_ms=(time.time() - start) * 1000,
        )
