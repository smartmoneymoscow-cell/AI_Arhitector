"""
shared/agents/mep_bpy.py — Генерация bpy-скрипта инженерных систем (MEP).

3D визуализация:
- Водоснабжение (ХВС/ГВС — трубы)
- Канализация (сливы — трубы с уклоном)
- Электрика (кабель-трассы, щит)
- Вентиляция (воздуховоды)
- Отопление (трубы, радиаторы)
"""


def generate_mep_bpy(params: dict, mep_calc: dict) -> str:
    """
    Генерирует bpy-скрипт для 3D визуализации инженерных систем.

    Args:
        params: параметры здания
        mep_calc: результат MEPAgent._design_all()

    Returns:
        bpy-скрипт для Blender
    """
    width = params.get("width_m", params.get("width", 10))
    length = params.get("length_m", params.get("length", 12))
    height = params.get("height_m", params.get("height", 3.0))
    floors = params.get("floors", 1)

    electrical = mep_calc.get("electrical", {})
    plumbing = mep_calc.get("plumbing", {})
    hvac = mep_calc.get("hvac", {})

    lines = [
        "import bpy",
        "import math",
        "",
        "# ═══════════════════════════════════════════",
        "# MEP SYSTEMS — 3D Visualization",
        "# ═══════════════════════════════════════════",
        "",
    ]

    # Materials
    lines.append(_mep_materials())

    # Plumbing (water supply + sewerage)
    lines.append(_plumbing_bpy(width, length, height, floors, plumbing))

    # Electrical
    lines.append(_electrical_bpy(width, length, height, floors, electrical))

    # HVAC (ventilation + heating)
    lines.append(_hvac_bpy(width, length, height, floors, hvac))

    return "\n".join(lines)


def _mep_materials() -> str:
    """Материалы для инженерных систем."""
    return """
# ═══ MEP Materials ═══

# Cold water pipe (blue)
mat_cold_water = bpy.data.materials.new("Pipe_ColdWater")
mat_cold_water.use_nodes = True
bsdf = mat_cold_water.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.1, 0.3, 0.8, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.3
    bsdf.inputs["Metallic"].default_value = 0.7

# Hot water pipe (red)
mat_hot_water = bpy.data.materials.new("Pipe_HotWater")
mat_hot_water.use_nodes = True
bsdf = mat_hot_water.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.8, 0.1, 0.1, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.3
    bsdf.inputs["Metallic"].default_value = 0.7

# Sewer pipe (brown/dark)
mat_sewer = bpy.data.materials.new("Pipe_Sewer")
mat_sewer.use_nodes = True
bsdf = mat_sewer.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.35, 0.25, 0.15, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.6
    bsdf.inputs["Metallic"].default_value = 0.1

# Electrical cable (yellow-green)
mat_cable = bpy.data.materials.new("Cable_Electrical")
mat_cable.use_nodes = True
bsdf = mat_cable.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.2, 0.6, 0.2, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.5
    bsdf.inputs["Metallic"].default_value = 0.3

# Duct (gray)
mat_duct = bpy.data.materials.new("Duct_Ventilation")
mat_duct.use_nodes = True
bsdf = mat_duct.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.7, 0.7, 0.72, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.4
    bsdf.inputs["Metallic"].default_value = 0.6

# Radiator (white)
mat_radiator = bpy.data.materials.new("Radiator")
mat_radiator.use_nodes = True
bsdf = mat_radiator.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.9, 0.9, 0.9, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.3
    bsdf.inputs["Metallic"].default_value = 0.8

# Electrical panel (gray metal)
mat_panel = bpy.data.materials.new("ElectricalPanel")
mat_panel.use_nodes = True
bsdf = mat_panel.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.5, 0.5, 0.55, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.3
    bsdf.inputs["Metallic"].default_value = 0.9
"""


def _plumbing_bpy(width: float, length: float, height: float, floors: int, plumbing: dict) -> str:
    """Генерация водоснабжения и канализации."""
    cold_pipe = plumbing.get("cold_water", {}).get("pipe", "Ду 25")
    hot_pipe = plumbing.get("hot_water", {}).get("pipe", "Ду 20")
    sewer_pipe = plumbing.get("sewerage", {}).get("pipe", "Ду 110")

    # Pipe diameters (approximate mm → m)
    cold_r = 0.0125  # Ду25 = 25mm diameter
    hot_r = 0.010  # Ду20
    sewer_r = 0.055  # Ду110

    lines = [
        f"# ═══ Plumbing: Water Supply + Sewerage ═══",
        f"# Cold: {cold_pipe}, Hot: {hot_pipe}, Sewer: {sewer_pipe}",
        "",
    ]

    for fl in range(floors):
        z = height * fl + height * 0.4  # pipes at 40% height

        # Cold water riser (blue, left side)
        lines.append(f"# Cold water riser floor {fl + 1}")
        lines.append(
            f"bpy.ops.mesh.primitive_cylinder_add(radius={cold_r}, depth={height}, location=(-{width}/2 + 0.3, -{length}/2 + 0.3, {z}))"
        )
        lines.append(f"cw = bpy.context.active_object; cw.name = 'ColdWater_Riser_F{fl + 1}'")
        lines.append(f"cw.data.materials.append(mat_cold_water)")

        # Hot water riser (red, left side)
        lines.append(f"# Hot water riser floor {fl + 1}")
        lines.append(
            f"bpy.ops.mesh.primitive_cylinder_add(radius={hot_r}, depth={height}, location=(-{width}/2 + 0.5, -{length}/2 + 0.3, {z}))"
        )
        lines.append(f"hw = bpy.context.active_object; hw.name = 'HotWater_Riser_F{fl + 1}'")
        lines.append(f"hw.data.materials.append(mat_hot_water)")

        # Horizontal branches to bathroom/kitchen
        lines.append(f"# Water branches to bathroom")
        lines.append(
            f"bpy.ops.mesh.primitive_cylinder_add(radius={cold_r}, depth={width}/2, location=(-{width}/4, -{length}/2 + 0.3, {z}))"
        )
        lines.append(f"cwb = bpy.context.active_object; cwb.name = 'ColdWater_Branch_F{fl + 1}'")
        lines.append(f"cwb.rotation_euler[1] = math.radians(90)")
        lines.append(f"cwb.data.materials.append(mat_cold_water)")

        # Sewer riser (brown, larger diameter)
        lines.append(f"# Sewer riser floor {fl + 1}")
        lines.append(
            f"bpy.ops.mesh.primitive_cylinder_add(radius={sewer_r}, depth={height}, location=(-{width}/2 + 0.3, -{length}/2 + 0.6, {z}))"
        )
        lines.append(f"sw = bpy.context.active_object; sw.name = 'Sewer_Riser_F{fl + 1}'")
        lines.append(f"sw.data.materials.append(mat_sewer)")

        # Sewer branch with slope
        lines.append(f"# Sewer branch (with slope)")
        lines.append(
            f"bpy.ops.mesh.primitive_cylinder_add(radius={sewer_r}, depth={width}/2, location=(-{width}/4, -{length}/2 + 0.6, {z} - 0.05))"
        )
        lines.append(f"swb = bpy.context.active_object; swb.name = 'Sewer_Branch_F{fl + 1}'")
        lines.append(f"swb.rotation_euler[1] = math.radians(90)")
        lines.append(f"swb.rotation_euler[2] = math.radians(-2)  # slope")
        lines.append(f"swb.data.materials.append(mat_sewer)")
        lines.append("")

    # Main sewer outlet
    lines.append(f"# Main sewer outlet (underground)")
    lines.append(
        f"bpy.ops.mesh.primitive_cylinder_add(radius={sewer_r}, depth={width} + 2, location=(0, -{length}/2 - 1, -0.3))"
    )
    lines.append(f"msw = bpy.context.active_object; msw.name = 'Sewer_Main'")
    lines.append(f"msw.rotation_euler[1] = math.radians(90)")
    lines.append(f"msw.data.materials.append(mat_sewer)")
    lines.append("")

    return "\n".join(lines)


def _electrical_bpy(width: float, length: float, height: float, floors: int, electrical: dict) -> str:
    """Генерация электрики."""
    main_breaker = electrical.get("main_breaker_a", 25)
    groups = electrical.get("groups", [])
    total_load = electrical.get("total_load_kw", 0)

    lines = [
        f"# ═══ Electrical: {total_load}kW, {main_breaker}A main breaker ═══",
        "",
    ]

    # Electrical panel
    lines.append(f"# Electrical panel (near entrance)")
    lines.append(f"bpy.ops.mesh.primitive_cube_add(size=1, location=(-{width}/2 + 0.15, 0, {height} * 0.6))")
    lines.append(f"panel = bpy.context.active_object; panel.name = 'ElectricalPanel'")
    lines.append(f"panel.scale = (0.08, 0.3, 0.4)")
    lines.append(f"bpy.ops.object.transform_apply(scale=True)")
    lines.append(f"panel.data.materials.append(mat_panel)")
    lines.append("")

    for fl in range(floors):
        z_base = height * fl

        # Cable tray (main trunk)
        lines.append(f"# Cable trunk floor {fl + 1}")
        lines.append(
            f"bpy.ops.mesh.primitive_cube_add(size=1, location=(-{width}/2 + 0.15, 0, {z_base} + {height} - 0.1))"
        )
        lines.append(f"tray = bpy.context.active_object; tray.name = 'CableTray_F{fl + 1}'")
        lines.append(f"tray.scale = (0.02, {length}/2, 0.02)")
        lines.append(f"bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"tray.data.materials.append(mat_cable)")
        lines.append("")

        # Branch cables to rooms
        lines.append(f"# Branch cables floor {fl + 1}")
        lines.append(f"for room_x in [-{width}/3, 0, {width}/3]:")
        lines.append(
            f"    bpy.ops.mesh.primitive_cylinder_add(radius=0.005, depth={length}/2, location=(room_x, 0, {z_base} + {height} - 0.1))"
        )
        lines.append(f"    cab = bpy.context.active_object; cab.name = f'Cable_Branch_{{room_x}}'")
        lines.append(f"    cab.rotation_euler[0] = math.radians(90)")
        lines.append(f"    cab.data.materials.append(mat_cable)")

        # Sockets (small cubes on walls)
        lines.append(f"# Sockets floor {fl + 1}")
        lines.append(f"for sx in [-{width}/3, 0, {width}/3]:")
        lines.append(f"    bpy.ops.mesh.primitive_cube_add(size=1, location=(sx, -{length}/2 - 0.01, {z_base} + 0.3))")
        lines.append(f"    sock = bpy.context.active_object; sock.name = f'Socket'")
        lines.append(f"    sock.scale = (0.04, 0.02, 0.04)")
        lines.append(f"    bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"    sock.data.materials.append(mat_panel)")
        lines.append("")

    return "\n".join(lines)


def _hvac_bpy(width: float, length: float, height: float, floors: int, hvac: dict) -> str:
    """Генерация вентиляции и отопления."""
    vent = hvac.get("ventilation", {})
    heating = hvac.get("heating", {})
    cooling = hvac.get("cooling", {})

    air_flow = vent.get("air_flow_m3h", 0)
    heat_load = heating.get("heat_load_kw", 0)

    lines = [
        f"# ═══ HVAC: Ventilation {air_flow}m³/h, Heating {heat_load}kW ═══",
        "",
    ]

    for fl in range(floors):
        z_vent = height * (fl + 1) - 0.15  # under ceiling

        # Main duct (rectangular, along building)
        lines.append(f"# Main ventilation duct floor {fl + 1}")
        lines.append(f"bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, {z_vent}))")
        lines.append(f"duct = bpy.context.active_object; duct.name = 'MainDuct_F{fl + 1}'")
        lines.append(f"duct.scale = ({width}/2, 0.2, 0.1)")
        lines.append(f"bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"duct.data.materials.append(mat_duct)")

        # Branch ducts
        lines.append(f"# Branch ducts floor {fl + 1}")
        lines.append(f"for bx in [-{width}/3, 0, {width}/3]:")
        lines.append(f"    bpy.ops.mesh.primitive_cube_add(size=1, location=(bx, 0, {z_vent}))")
        lines.append(f"    bd = bpy.context.active_object; bd.name = f'BranchDuct'")
        lines.append(f"    bd.scale = (0.08, {length}/3, 0.08)")
        lines.append(f"    bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"    bd.data.materials.append(mat_duct)")

        # Supply grilles
        lines.append(f"# Supply grilles floor {fl + 1}")
        lines.append(f"for gx in [-{width}/3, {width}/3]:")
        lines.append(f"    bpy.ops.mesh.primitive_cube_add(size=1, location=(gx, 0, {z_vent} - 0.08))")
        lines.append(f"    gr = bpy.context.active_object; gr.name = f'Grille'")
        lines.append(f"    gr.scale = (0.15, 0.15, 0.01)")
        lines.append(f"    bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"    gr.data.materials.append(mat_duct)")

        # Radiators (under windows)
        lines.append(f"# Radiators floor {fl + 1}")
        lines.append(f"for rx in [-{width}/3, 0, {width}/3]:")
        lines.append(
            f"    bpy.ops.mesh.primitive_cube_add(size=1, location=(rx, -{length}/2 - 0.05, {height} * {fl} + 0.3))"
        )
        lines.append(f"    rad = bpy.context.active_object; rad.name = f'Radiator'")
        lines.append(f"    rad.scale = (0.4, 0.05, 0.3)")
        lines.append(f"    bpy.ops.object.transform_apply(scale=True)")
        lines.append(f"    rad.data.materials.append(mat_radiator)")

        # Heating pipes
        lines.append(f"# Heating pipes floor {fl + 1}")
        lines.append(f"for px in [-{width}/3, {width}/3]:")
        lines.append(
            f"    bpy.ops.mesh.primitive_cylinder_add(radius=0.01, depth=0.6, location=(px, -{length}/2 - 0.05, {height} * {fl} + 0.6))"
        )
        lines.append(f"    hp = bpy.context.active_object; hp.name = f'HeatPipe'")
        lines.append(f"    hp.data.materials.append(mat_hot_water)")
        lines.append("")

    # External unit (condenser)
    lines.append(f"# External AC unit")
    lines.append(f"bpy.ops.mesh.primitive_cube_add(size=1, location=({width}/2 + 1, 0, 1))")
    lines.append(f"ac = bpy.context.active_object; ac.name = 'AC_External'")
    lines.append(f"ac.scale = (0.4, 0.6, 0.3)")
    lines.append(f"bpy.ops.object.transform_apply(scale=True)")
    lines.append(f"ac.data.materials.append(mat_duct)")
    lines.append("")

    return "\n".join(lines)
