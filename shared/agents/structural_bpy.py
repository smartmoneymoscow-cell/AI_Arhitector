"""
shared/agents/structural_bpy.py — Генерация bpy-скрипта реалистичного каркаса.

Интегрирует расчёты structural_agent.py в визуализацию:
- Фундамент (ленточный, плитный, свайный)
- Колонны и балки каркаса
- Перекрытия (монолитные, пустотные)
- Стропильная система
- Армирование

Все элементы создаются как 3D-мешы в Blender.
"""

import math


def generate_structural_bpy(params: dict, structural_calc: dict) -> str:
    """
    Генерирует bpy-скрипт для визуализации конструктива.

    Args:
        params: параметры здания (width, length, height, floors, material)
        structural_calc: результат structural_agent._calculate_structure()

    Returns:
        bpy-скрипт для Blender
    """
    width = params.get("width_m", params.get("width", 10))
    length = params.get("length_m", params.get("length", 12))
    height = params.get("height_m", params.get("height", 3.0))
    floors = params.get("floors", 2)
    material = params.get("material", "brick").lower()

    foundation = structural_calc.get("foundation", {})
    walls = structural_calc.get("walls", {})
    floors_design = structural_calc.get("floors", [])
    roof = structural_calc.get("roof", {})
    stairs = structural_calc.get("stairs", {})

    lines = [
        "import bpy",
        "import math",
        "",
        "# ═══════════════════════════════════════════",
        "# STRUCTURAL FRAME — Realistic Construction",
        "# ═══════════════════════════════════════════",
        "",
    ]

    # Materials
    lines.append(_structural_materials())

    # Foundation
    lines.append(_foundation_bpy(width, length, foundation))

    # Columns (for multi-story or large buildings)
    if floors >= 2 or width > 15:
        lines.append(_columns_bpy(width, length, height, floors))

    # Beams (ring beam / armo-poyas)
    lines.append(_beams_bpy(width, length, height, floors, material))

    # Floor slabs
    if floors > 1:
        lines.append(_floor_slabs_bpy(width, length, height, floors, floors_design))

    # Walls with proper thickness
    lines.append(_walls_bpy(width, length, height, floors, walls, material))

    # Roof structure
    lines.append(_roof_structure_bpy(width, length, height, floors, roof))

    # Stairs
    if floors > 1 and stairs:
        lines.append(_stairs_bpy(width, length, height, floors, stairs))

    # Rebar visualization (inside foundation and beams)
    lines.append(_rebar_bpy(width, length, foundation))

    return "\n".join(lines)


def _structural_materials() -> str:
    """Материалы для конструктивных элементов."""
    return """
# ═══ Structural Materials ═══
mat_concrete = bpy.data.materials.new("Concrete_Struct")
mat_concrete.use_nodes = True
bsdf = mat_concrete.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.6, 0.6, 0.58, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.9
    bsdf.inputs["Metallic"].default_value = 0.0

mat_rebar = bpy.data.materials.new("Rebar_A500C")
mat_rebar.use_nodes = True
bsdf_r = mat_rebar.node_tree.nodes.get("Principled BSDF")
if bsdf_r:
    bsdf_r.inputs["Base Color"].default_value = (0.2, 0.2, 0.22, 1.0)
    bsdf_r.inputs["Roughness"].default_value = 0.4
    bsdf_r.inputs["Metallic"].default_value = 0.8

mat_steel = bpy.data.materials.new("Steel_Beam")
mat_steel.use_nodes = True
bsdf_s = mat_steel.node_tree.nodes.get("Principled BSDF")
if bsdf_s:
    bsdf_s.inputs["Base Color"].default_value = (0.3, 0.3, 0.35, 1.0)
    bsdf_s.inputs["Roughness"].default_value = 0.3
    bsdf_s.inputs["Metallic"].default_value = 0.9

mat_wood_structure = bpy.data.materials.new("Wood_Struct")
mat_wood_structure.use_nodes = True
bsdf_w = mat_wood_structure.node_tree.nodes.get("Principled BSDF")
if bsdf_w:
    bsdf_w.inputs["Base Color"].default_value = (0.55, 0.35, 0.18, 1.0)
    bsdf_w.inputs["Roughness"].default_value = 0.75
    bsdf_w.inputs["Metallic"].default_value = 0.0

mat_insulation = bpy.data.materials.new("Insulation")
mat_insulation.use_nodes = True
bsdf_i = mat_insulation.node_tree.nodes.get("Principled BSDF")
if bsdf_i:
    bsdf_i.inputs["Base Color"].default_value = (0.95, 0.95, 0.4, 1.0)
    bsdf_i.inputs["Roughness"].default_value = 1.0
    bsdf_i.inputs["Metallic"].default_value = 0.0
"""


def _foundation_bpy(width: float, length: float, foundation: dict) -> str:
    """Генерация фундамента."""
    ftype = foundation.get("type", "strip")
    depth = foundation.get("depth_m", 1.2)
    fwidth = foundation.get("width_m", 0.4)

    lines = [
        f"# ═══ Foundation: {ftype} ═══",
        f"# depth={depth}m, width={fwidth}m",
        "",
    ]

    if ftype == "strip":
        # Ленточный фундамент — 4 ленты по периметру
        perimeter = 2 * (width + length)
        lines.append(f"# Strip foundation ({foundation.get('description', 'monolithic')})")
        lines.append(f"for dx, dy, sx, sy in [")
        lines.append(f"    (0, -{length}/2, {width}, {fwidth}),   # front")
        lines.append(f"    (0, {length}/2, {width}, {fwidth}),    # back")
        lines.append(f"    (-{width}/2, 0, {fwidth}, {length}),   # left")
        lines.append(f"    ({width}/2, 0, {fwidth}, {length}),    # right")
        lines.append(f"]:")
        lines.append(f"    bpy.ops.mesh.primitive_cube_add(size=1, location=(dx, dy, -{depth}/2))")
        lines.append(f"    fnd = bpy.context.active_object")
        lines.append(f"    fnd.name = 'Foundation_Strip'")
        lines.append(f"    fnd.scale = (sx/2, sy/2, {depth}/2)")
        lines.append(f"    bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"    fnd.data.materials.append(mat_concrete)")
        lines.append("")
        # Подушка
        lines.append(f"# Foundation pad (gravel)")
        lines.append(f"bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -{depth} - 0.15))")
        lines.append(f"pad = bpy.context.active_object; pad.name = 'Foundation_Pad'")
        lines.append(f"pad.scale = ({width}/2 + 0.3, {length}/2 + 0.3, 0.15)")
        lines.append(f"bpy.ops.object.transform_apply(scale=True)")

    elif ftype == "slab":
        # Плитный фундамент
        lines.append(f"# Slab foundation")
        lines.append(f"bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -{depth}/2))")
        lines.append(f"slab = bpy.context.active_object; slab.name = 'Foundation_Slab'")
        lines.append(f"slab.scale = ({width}/2 + 0.3, {length}/2 + 0.3, {depth}/2)")
        lines.append(f"bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"slab.data.materials.append(mat_concrete)")

    elif ftype == "pile":
        # Свайный фундамент
        pile_spacing = 2.0
        nx = max(2, int(width / pile_spacing) + 1)
        ny = max(2, int(length / pile_spacing) + 1)
        lines.append(f"# Pile foundation ({nx}x{ny} piles)")
        lines.append(f"for ix in range({nx}):")
        lines.append(f"    for iy in range({ny}):")
        lines.append(f"        px = -{width}/2 + ix * ({width}/({nx}-1))")
        lines.append(f"        py = -{length}/2 + iy * ({length}/({ny}-1))")
        lines.append(
            f"        bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth={depth}, location=(px, py, -{depth}/2))"
        )
        lines.append(f"        pile = bpy.context.active_object; pile.name = f'Pile_{{ix}}_{{iy}}'")
        lines.append(f"        pile.data.materials.append(mat_concrete)")
        lines.append(f"# Pile cap (ростверк)")
        lines.append(f"bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.15))")
        lines.append(f"cap = bpy.context.active_object; cap.name = 'Pile_Cap'")
        lines.append(f"cap.scale = ({width}/2, {length}/2, 0.15)")
        lines.append(f"bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"cap.data.materials.append(mat_concrete)")

    lines.append("")
    return "\n".join(lines)


def _columns_bpy(width: float, length: float, height: float, floors: int) -> str:
    """Генерация колонн каркаса."""
    total_h = height * floors
    col_section = 0.3 if floors <= 3 else 0.4

    # Колонны по периметру с шагом 3-4м
    spacing = min(4.0, width / 2)
    nx = max(2, int(width / spacing) + 1)
    ny = max(2, int(length / spacing) + 1)

    lines = [
        f"# ═══ Columns (frame structure) ═══",
        f"# Section: {col_section}x{col_section}m, height: {total_h}m",
        f"col_section = {col_section}",
        f"for ix in range({nx}):",
        f"    for iy in range({ny}):",
        f"        cx = -{width}/2 + ix * ({width}/({nx}-1))",
        f"        cy = -{length}/2 + iy * ({length}/({ny}-1))",
        f"        bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, {total_h}/2))",
        f"        col = bpy.context.active_object; col.name = f'Column_{{ix}}_{{iy}}'",
        f"        col.scale = (col_section/2, col_section/2, {total_h}/2)",
        f"        bpy.ops.object.transform_apply(scale=True)",
        f"        col.data.materials.append(mat_concrete)",
        "",
    ]
    return "\n".join(lines)


def _beams_bpy(width: float, length: float, height: float, floors: int, material: str) -> str:
    """Генерация балок (армопояс, ригели)."""
    beam_h = 0.3
    beam_w = 0.3

    lines = [
        f"# ═══ Beams (ring beam / armo-poyas) ═══",
    ]

    for fl in range(floors):
        z = height * (fl + 1)
        lines.append(f"# Floor {fl + 1} ring beam at z={z}m")
        # Front and back beams
        lines.append(f"for dy in [-{length}/2, {length}/2]:")
        lines.append(f"    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, dy, {z} - {beam_h}/2))")
        lines.append(f"    bm = bpy.context.active_object; bm.name = f'Beam_F{{fl}}'")
        lines.append(f"    bm.scale = ({width}/2, {beam_w}/2, {beam_h}/2)")
        lines.append(f"    bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"    bm.data.materials.append(mat_concrete)")
        # Left and right beams
        lines.append(f"for dx in [-{width}/2, {width}/2]:")
        lines.append(f"    bpy.ops.mesh.primitive_cube_add(size=1, location=(dx, 0, {z} - {beam_h}/2))")
        lines.append(f"    bm = bpy.context.active_object; bm.name = f'Beam_S{{fl}}'")
        lines.append(f"    bm.scale = ({beam_w}/2, {length}/2, {beam_h}/2)")
        lines.append(f"    bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"    bm.data.materials.append(mat_concrete)")
        lines.append("")

    return "\n".join(lines)


def _floor_slabs_bpy(width: float, length: float, height: float, floors: int, floors_design: list) -> str:
    """Генерация перекрытий."""
    lines = [f"# ═══ Floor Slabs ═══"]

    for i, fd in enumerate(floors_design):
        fl = fd.get("floor", i + 1)
        thickness = fd.get("thickness_m", 0.2)
        slab_type = fd.get("type", "Монолитная плита")

        z = height * fl
        lines.append(f"# Floor {fl} slab: {slab_type} ({thickness}m)")
        lines.append(f"bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, {z} - {thickness}/2))")
        lines.append(f"slab_{fl} = bpy.context.active_object; slab_{fl}.name = 'Slab_F{fl}'")
        lines.append(f"slab_{fl}.scale = ({width}/2, {length}/2, {thickness}/2)")
        lines.append(f"bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"slab_{fl}.data.materials.append(mat_concrete)")
        lines.append("")

    return "\n".join(lines)


def _walls_bpy(width: float, length: float, height: float, floors: int, walls: dict, material: str) -> str:
    """Генерация стен с правильной толщиной."""
    thickness = walls.get("thickness_m", 0.3)
    total_h = height * floors

    mat_map = {
        "brick": ("mat_brick", "(0.7, 0.35, 0.2, 1.0)"),
        "кирпич": ("mat_brick", "(0.7, 0.35, 0.2, 1.0)"),
        "wood": ("mat_wood", "(0.6, 0.4, 0.2, 1.0)"),
        "дерево": ("mat_wood", "(0.6, 0.4, 0.2, 1.0)"),
        "concrete": ("mat_concrete_wall", "(0.55, 0.55, 0.53, 1.0)"),
        "бетон": ("mat_concrete_wall", "(0.55, 0.55, 0.53, 1.0)"),
        "foam_block": ("mat_foam", "(0.85, 0.82, 0.75, 1.0)"),
        "пеноблок": ("mat_foam", "(0.85, 0.82, 0.75, 1.0)"),
    }
    mat_name, mat_color = mat_map.get(material, ("mat_wall", "(0.85, 0.82, 0.75, 1.0)"))

    lines = [
        f"# ═══ Walls (thickness: {thickness}m) ═══",
        f"# {walls.get('description', 'Standard walls')}",
        f"mat_wall = bpy.data.materials.new('Wall_{material}')",
        f"mat_wall.use_nodes = True",
        f"bsdf_w = mat_wall.node_tree.nodes.get('Principled BSDF')",
        f"if bsdf_w: bsdf_w.inputs['Base Color'].default_value = {mat_color}",
        "",
    ]

    # 4 walls
    wall_defs = [
        (
            f"(0, -{length}/2 - {thickness}/2, {total_h}/2)",
            f"({width}/2 + {thickness}, {thickness}/2, {total_h}/2)",
            "Front",
        ),
        (
            f"(0, {length}/2 + {thickness}/2, {total_h}/2)",
            f"({width}/2 + {thickness}, {thickness}/2, {total_h}/2)",
            "Back",
        ),
        (f"(-{width}/2 - {thickness}/2, 0, {total_h}/2)", f"({thickness}/2, {length}/2, {total_h}/2)", "Left"),
        (f"({width}/2 + {thickness}/2, 0, {total_h}/2)", f"({thickness}/2, {length}/2, {total_h}/2)", "Right"),
    ]

    for loc, scale, name in wall_defs:
        lines.append(f"bpy.ops.mesh.primitive_cube_add(size=1, location={loc})")
        lines.append(f"w = bpy.context.active_object; w.name = 'Wall_{name}'")
        lines.append(f"w.scale = {scale}")
        lines.append(f"bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"w.data.materials.append(mat_wall)")
        lines.append("")

    return "\n".join(lines)


def _roof_structure_bpy(width: float, length: float, height: float, floors: int, roof: dict) -> str:
    """Генерация стропильной системы."""
    roof_type = roof.get("type", "Двускатная крыша")
    slope = roof.get("slope_angle", 35)
    rafter_section = roof.get("rafter_section", "50x200")
    rafter_step = roof.get("rafter_step_m", 0.6)

    z_base = height * floors
    rafter_len = (width / 2) / math.cos(math.radians(slope))

    lines = [
        f"# ═══ Roof Structure: {roof_type} ═══",
        f"# Slope: {slope}°, Rafter: {rafter_section}mm, Step: {rafter_step}m",
        f"mat_roof_wood = bpy.data.materials.new('RoofWood')",
        f"mat_roof_wood.use_nodes = True",
        f"bsdf_rw = mat_roof_wood.node_tree.nodes.get('Principled BSDF')",
        f"if bsdf_rw: bsdf_rw.inputs['Base Color'].default_value = (0.45, 0.28, 0.12, 1.0)",
        "",
    ]

    if "двускатн" in roof_type.lower() or "gable" in roof_type.lower():
        # Ridge beam
        lines.append(f"# Ridge beam")
        lines.append(
            f"bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, {z_base} + {rafter_len} * math.sin(math.radians({slope}))/2))"
        )
        lines.append(f"ridge = bpy.context.active_object; ridge.name = 'Ridge_Beam'")
        lines.append(f"ridge.scale = (0.05, {length}/2, 0.05)")
        lines.append(f"bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"ridge.data.materials.append(mat_roof_wood)")
        lines.append("")

        # Rafters
        lines.append(f"# Rafters")
        lines.append(f"rafter_step = {rafter_step}")
        lines.append(f"n_rafters = int({length} / rafter_step) + 1")
        lines.append(f"for i in range(n_rafters):")
        lines.append(f"    y = -{length}/2 + i * rafter_step")
        lines.append(f"    # Left rafter")
        lines.append(f"    bpy.ops.mesh.primitive_cube_add(size=1)")
        lines.append(f"    r = bpy.context.active_object; r.name = f'Rafter_L_{{i}}'")
        lines.append(f"    r.location = (-{width}/4, y, {z_base} + {rafter_len} * math.sin(math.radians({slope}))/2)")
        lines.append(f"    r.scale = (0.025, 0.05, {rafter_len}/2)")
        lines.append(f"    bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"    r.rotation_euler[1] = math.radians({slope})")
        lines.append(f"    r.data.materials.append(mat_roof_wood)")
        lines.append(f"    # Right rafter")
        lines.append(f"    bpy.ops.mesh.primitive_cube_add(size=1)")
        lines.append(f"    r2 = bpy.context.active_object; r2.name = f'Rafter_R_{{i}}'")
        lines.append(f"    r2.location = ({width}/4, y, {z_base} + {rafter_len} * math.sin(math.radians({slope}))/2)")
        lines.append(f"    r2.scale = (0.025, 0.05, {rafter_len}/2)")
        lines.append(f"    bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"    r2.rotation_euler[1] = -math.radians({slope})")
        lines.append(f"    r2.data.materials.append(mat_roof_wood)")
        lines.append("")

        # Mauerlat (support beam)
        lines.append(f"# Mauerlat (support beam)")
        lines.append(f"for dy in [-{length}/2, {length}/2]:")
        lines.append(f"    for dx in [-{width}/2, {width}/2]:")
        lines.append(f"        bpy.ops.mesh.primitive_cube_add(size=1, location=(dx, dy, {z_base} + 0.05))")
        lines.append(f"        ml = bpy.context.active_object; ml.name = 'Mauerlat'")
        lines.append(f"        ml.scale = (0.05, 0.05, 0.05)")
        lines.append(f"        bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"        ml.data.materials.append(mat_roof_wood)")

    elif "flat" in roof_type.lower() or "плоск" in roof_type.lower():
        lines.append(f"# Flat roof slab")
        lines.append(f"bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, {z_base} + 0.15))")
        lines.append(f"roof_slab = bpy.context.active_object; roof_slab.name = 'Roof_Slab'")
        lines.append(f"roof_slab.scale = ({width}/2 + 0.3, {length}/2 + 0.3, 0.15)")
        lines.append(f"bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"roof_slab.data.materials.append(mat_concrete)")

    lines.append("")
    return "\n".join(lines)


def _stairs_bpy(width: float, length: float, height: float, floors: int, stairs: dict) -> str:
    """Генерация лестницы."""
    num_steps = stairs.get("num_steps", 12)
    riser = stairs.get("riser_height_m", 0.17)
    tread = stairs.get("tread_depth_m", 0.28)
    stair_w = stairs.get("width_m", 1.0)

    lines = [
        f"# ═══ Staircase ═══",
        f"# {stairs.get('type', 'П-образная')}: {num_steps} steps",
        f"for s in range({num_steps}):",
        f"    bpy.ops.mesh.primitive_cube_add(size=1, location=({width}/2 - 0.6, -{length}/2 + 0.3 + s * {tread}, s * {riser} + {riser}/2))",
        f"    step = bpy.context.active_object; step.name = f'Step_{{s}}'",
        f"    step.scale = ({stair_w}/2, {tread}/2, {riser}/2)",
        f"    bpy.ops.object.transform_apply(scale=True)",
        f"    step.data.materials.append(mat_concrete)",
        "",
    ]
    return "\n".join(lines)


def _rebar_bpy(width: float, length: float, foundation: dict) -> str:
    """Визуализация арматуры (только внутри конструктивных элементов)."""
    ftype = foundation.get("type", "strip")
    rebar_spec = foundation.get("rebar", "А500С ∅12, шаг 200мм")

    lines = [
        f"# ═══ Rebar (visualization only) ═══",
        f"# Spec: {rebar_spec}",
        f"rebar_r = 0.006  # ∅12mm radius",
        "",
    ]

    if ftype == "strip":
        # Арматура в ленточном фундаменте
        depth = foundation.get("depth_m", 1.2)
        lines.append(f"# Longitudinal rebar in strip foundation")
        lines.append(f"for dy in [-{length}/2, {length}/2]:")
        lines.append(f"    for iz in range(3):  # 3 layers")
        lines.append(
            f"        bpy.ops.mesh.primitive_cylinder_add(radius=rebar_r, depth={width}, location=(0, dy, -{depth} + 0.1 + iz * 0.15))"
        )
        lines.append(f"        rb = bpy.context.active_object; rb.name = f'Rebar_H_{{iz}}'")
        lines.append(f"        rb.rotation_euler[1] = math.radians(90)")
        lines.append(f"        rb.data.materials.append(mat_rebar)")
    elif ftype == "pile":
        lines.append(f"# Rebar cage in piles")
        lines.append(f"# (simplified — vertical bars only)")
    else:
        lines.append(f"# Slab rebar mesh")
        lines.append(f"# (simplified — grid pattern)")

    lines.append("")
    return "\n".join(lines)
