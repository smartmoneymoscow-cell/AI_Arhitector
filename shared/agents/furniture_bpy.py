"""
shared/agents/furniture_bpy.py — Высококачественная мебель для Blender.

Генерирует детализированные bpy-скрипты для мебели с:
- PBR-материалами (дерево, ткань, кожа, металл)
- Правильными пропорциями
- Мягкой мебелью (подушки, обивка)
- Фурнитурой (ручки, ножки)
"""


def generate_furniture_bpy(room_type: str, furniture_list: list, room_w: float, room_l: float, style: str = "modern") -> str:
    """
    Генерирует bpy-скрипт высококачественной мебели.

    Args:
        room_type: тип комнаты
        furniture_list: список предметов мебели
        room_w, room_l: размеры комнаты
        style: стиль интерьера

    Returns:
        bpy-скрипт
    """
    lines = [
        "import bpy",
        "import math",
        "",
        "# ═══════════════════════════════════════════",
        f"# HIGH-QUALITY FURNITURE — {room_type} ({style})",
        "# ═══════════════════════════════════════════",
        "",
    ]

    # Materials
    lines.append(_furniture_materials(style))

    # Generate each furniture item
    x_cursor = 0.5
    y_cursor = 0.5

    for item_name in furniture_list:
        item_lower = item_name.lower().replace(" ", "_")
        gen_func = FURNITURE_GENERATORS.get(item_lower)
        if gen_func:
            lines.append(gen_func(x_cursor, y_cursor, style))
            x_cursor += 2.0
            if x_cursor > room_w - 1.0:
                x_cursor = 0.5
                y_cursor += 2.0

    return "\n".join(lines)


def _furniture_materials(style: str) -> str:
    """Материалы для мебели."""
    style_colors = {
        "modern": {"wood": (0.4, 0.25, 0.12), "fabric": (0.7, 0.7, 0.7), "metal": (0.3, 0.3, 0.35)},
        "classic": {"wood": (0.55, 0.3, 0.12), "fabric": (0.6, 0.15, 0.1), "metal": (0.7, 0.6, 0.2)},
        "loft": {"wood": (0.5, 0.35, 0.2), "fabric": (0.4, 0.4, 0.4), "metal": (0.2, 0.2, 0.25)},
        "minimalist": {"wood": (0.85, 0.82, 0.75), "fabric": (0.9, 0.9, 0.9), "metal": (0.5, 0.5, 0.55)},
    }
    c = style_colors.get(style, style_colors["modern"])

    return f"""
# ═══ Furniture Materials ═══
mat_wood_furn = bpy.data.materials.new("Furniture_Wood")
mat_wood_furn.use_nodes = True
bsdf = mat_wood_furn.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = ({c['wood'][0]}, {c['wood'][1]}, {c['wood'][2]}, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.6
    bsdf.inputs["Metallic"].default_value = 0.0

mat_fabric = bpy.data.materials.new("Furniture_Fabric")
mat_fabric.use_nodes = True
bsdf = mat_fabric.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = ({c['fabric'][0]}, {c['fabric'][1]}, {c['fabric'][2]}, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.95
    bsdf.inputs["Metallic"].default_value = 0.0

mat_leather = bpy.data.materials.new("Furniture_Leather")
mat_leather.use_nodes = True
bsdf = mat_leather.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.35, 0.2, 0.1, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.4
    bsdf.inputs["Metallic"].default_value = 0.0

mat_metal_furn = bpy.data.materials.new("Furniture_Metal")
mat_metal_furn.use_nodes = True
bsdf = mat_metal_furn.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = ({c['metal'][0]}, {c['metal'][1]}, {c['metal'][2]}, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.3
    bsdf.inputs["Metallic"].default_value = 0.9

mat_glass_furn = bpy.data.materials.new("Furniture_Glass")
mat_glass_furn.use_nodes = True
bsdf = mat_glass_furn.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.9, 0.95, 1.0, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.05
    bsdf.inputs["Metallic"].default_value = 0.1
    bsdf.inputs["Alpha"].default_value = 0.3

mat_white = bpy.data.materials.new("White_Plastic")
mat_white.use_nodes = True
bsdf = mat_white.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.95, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.4
"""


def _gen_sofa(x, y, style):
    """Диван с подушками."""
    return f"""
# ═══ Sofa ═══
# Frame
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.25))
sofa_frame = bpy.context.active_object; sofa_frame.name = "Sofa_Frame"
sofa_frame.scale = (1.1, 0.45, 0.25)
bpy.ops.object.transform_apply(scale=True)
sofa_frame.data.materials.append(mat_fabric)
# Back
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y} - 0.4, 0.5))
sofa_back = bpy.context.active_object; sofa_back.name = "Sofa_Back"
sofa_back.scale = (1.1, 0.08, 0.25)
bpy.ops.object.transform_apply(scale=True)
sofa_back.data.materials.append(mat_fabric)
# Seat cushions (3)
for ci in range(3):
    bpy.ops.mesh.primitive_cube_add(size=1, location=({x} - 0.6 + ci * 0.6, {y}, 0.52))
    cushion = bpy.context.active_object; cushion.name = f"Sofa_Cushion_{{ci}}"
    cushion.scale = (0.25, 0.35, 0.05)
    bpy.ops.object.transform_apply(scale=True)
    cushion.data.materials.append(mat_fabric)
# Armrests
for side in [-1, 1]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=({x} + side * 1.05, {y}, 0.35))
    arm = bpy.context.active_object; arm.name = f"Sofa_Arm_{{side}}"
    arm.scale = (0.08, 0.4, 0.15)
    bpy.ops.object.transform_apply(scale=True)
    arm.data.materials.append(mat_fabric)
# Legs
for lx, ly in [(-1, -0.35), (-1, 0.35), (1, -0.35), (1, 0.35)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.025, depth=0.08, location=({x} + lx * 0.95, {y} + ly * 0.9, 0.04))
    leg = bpy.context.active_object; leg.name = "Sofa_Leg"
    leg.data.materials.append(mat_metal_furn)
"""


def _gen_table(x, y, style):
    """Стол."""
    return f"""
# ═══ Table ═══
# Top
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.75))
top = bpy.context.active_object; top.name = "Table_Top"
top.scale = (0.6, 0.4, 0.025)
bpy.ops.object.transform_apply(scale=True)
top.data.materials.append(mat_wood_furn)
# Legs
for lx, ly in [(-0.5, -0.3), (-0.5, 0.3), (0.5, -0.3), (0.5, 0.3)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.025, depth=0.73, location=({x} + lx, {y} + ly, 0.365))
    leg = bpy.context.active_object; leg.name = "Table_Leg"
    leg.data.materials.append(mat_metal_furn)
"""


def _gen_bed(x, y, style):
    """Кровать с изголовьем и матрасом."""
    return f"""
# ═══ Bed ═══
# Frame
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.2))
bed_frame = bpy.context.active_object; bed_frame.name = "Bed_Frame"
bed_frame.scale = (1.0, 0.9, 0.2)
bpy.ops.object.transform_apply(scale=True)
bed_frame.data.materials.append(mat_wood_furn)
# Mattress
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.42))
mattress = bpy.context.active_object; mattress.name = "Mattress"
mattress.scale = (0.95, 0.85, 0.12)
bpy.ops.object.transform_apply(scale=True)
mattress.data.materials.append(mat_white)
# Pillows
for px in [-0.3, 0.3]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=({x} + px, {y} - 0.65, 0.52))
    pillow = bpy.context.active_object; pillow.name = f"Pillow_{{px}}"
    pillow.scale = (0.2, 0.12, 0.05)
    bpy.ops.object.transform_apply(scale=True)
    pillow.data.materials.append(mat_white)
# Headboard
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y} - 0.85, 0.55))
headboard = bpy.context.active_object; headboard.name = "Headboard"
headboard.scale = (1.0, 0.05, 0.35)
bpy.ops.object.transform_apply(scale=True)
headboard.data.materials.append(mat_wood_furn)
# Blanket
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y} + 0.2, 0.5))
blanket = bpy.context.active_object; blanket.name = "Blanket"
blanket.scale = (0.9, 0.5, 0.03)
bpy.ops.object.transform_apply(scale=True)
blanket.data.materials.append(mat_fabric)
"""


def _gen_chair(x, y, style):
    """Стул."""
    return f"""
# ═══ Chair ═══
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.45))
seat = bpy.context.active_object; seat.name = "Chair_Seat"
seat.scale = (0.2, 0.2, 0.02)
bpy.ops.object.transform_apply(scale=True)
seat.data.materials.append(mat_wood_furn)
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y} - 0.18, 0.7))
back = bpy.context.active_object; back.name = "Chair_Back"
back.scale = (0.18, 0.02, 0.25)
bpy.ops.object.transform_apply(scale=True)
back.data.materials.append(mat_wood_furn)
for lx, ly in [(-0.15, -0.15), (-0.15, 0.15), (0.15, -0.15), (0.15, 0.15)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.015, depth=0.44, location=({x} + lx, {y} + ly, 0.22))
    leg = bpy.context.active_object; leg.name = "Chair_Leg"
    leg.data.materials.append(mat_metal_furn)
"""


def _gen_wardrobe(x, y, style):
    """Шкаф."""
    return f"""
# ═══ Wardrobe ═══
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 1.2))
ward = bpy.context.active_object; ward.name = "Wardrobe"
ward.scale = (0.9, 0.3, 1.2)
bpy.ops.object.transform_apply(scale=True)
ward.data.materials.append(mat_wood_furn)
# Doors (2)
for side in [-1, 1]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=({x} + side * 0.42, {y} - 0.31, 1.2))
    door = bpy.context.active_object; door.name = f"Wardrobe_Door_{{side}}"
    door.scale = (0.4, 0.02, 1.15)
    bpy.ops.object.transform_apply(scale=True)
    door.data.materials.append(mat_wood_furn)
    # Handle
    bpy.ops.mesh.primitive_cylinder_add(radius=0.01, depth=0.08, location=({x} + side * 0.42 - side * 0.3, {y} - 0.33, 1.2))
    handle = bpy.context.active_object; handle.name = "Wardrobe_Handle"
    handle.rotation_euler[0] = math.radians(90)
    handle.data.materials.append(mat_metal_furn)
"""


def _gen_bookshelf(x, y, style):
    """Книжный стеллаж."""
    return f"""
# ═══ Bookshelf ═══
# Sides
for side in [-1, 1]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=({x} + side * 0.4, {y}, 0.9))
    s = bpy.context.active_object; s.name = f"Bookshelf_Side_{{side}}"
    s.scale = (0.02, 0.25, 0.9)
    bpy.ops.object.transform_apply(scale=True)
    s.data.materials.append(mat_wood_furn)
# Shelves (5)
for sh in range(5):
    bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.05 + sh * 0.35))
    shelf = bpy.context.active_object; shelf.name = f"Bookshelf_Shelf_{{sh}}"
    shelf.scale = (0.4, 0.25, 0.015)
    bpy.ops.object.transform_apply(scale=True)
    shelf.data.materials.append(mat_wood_furn)
# Books (simplified as colored blocks)
for bi in range(8):
    bpy.ops.mesh.primitive_cube_add(size=1, location=({x} - 0.3 + bi * 0.08, {y}, 0.38))
    book = bpy.context.active_object; book.name = f"Book_{{bi}}"
    book.scale = (0.03, 0.18, 0.12)
    bpy.ops.object.transform_apply(scale=True)
    mat_book = bpy.data.materials.new(f"Book_{{bi}}")
    mat_book.use_nodes = True
    bsdf = mat_book.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        import random
        bsdf.inputs["Base Color"].default_value = (random.random() * 0.5 + 0.2, random.random() * 0.5 + 0.1, random.random() * 0.5 + 0.1, 1.0)
    book.data.materials.append(mat_book)
"""


def _gen_desk(x, y, style):
    """Рабочий стол."""
    return f"""
# ═══ Desk ═══
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.75))
desk_top = bpy.context.active_object; desk_top.name = "Desk_Top"
desk_top.scale = (0.7, 0.35, 0.025)
bpy.ops.object.transform_apply(scale=True)
desk_top.data.materials.append(mat_wood_furn)
# Legs
for lx, ly in [(-0.6, -0.28), (-0.6, 0.28), (0.6, -0.28), (0.6, 0.28)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=0.73, location=({x} + lx, {y} + ly, 0.365))
    leg = bpy.context.active_object; leg.name = "Desk_Leg"
    leg.data.materials.append(mat_metal_furn)
# Monitor
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y} - 0.25, 1.1))
mon = bpy.context.active_object; mon.name = "Monitor"
mon.scale = (0.3, 0.02, 0.2)
bpy.ops.object.transform_apply(scale=True)
mon.data.materials.append(mat_metal_furn)
# Monitor screen
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y} - 0.24, 1.1))
scr = bpy.context.active_object; scr.name = "Monitor_Screen"
scr.scale = (0.28, 0.005, 0.18)
bpy.ops.object.transform_apply(scale=True)
mat_screen = bpy.data.materials.new("Screen")
mat_screen.use_nodes = True
bsdf = mat_screen.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.1, 0.1, 0.15, 1.0)
    bsdf.inputs["Emission Color"].default_value = (0.2, 0.3, 0.5, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.5
scr.data.materials.append(mat_screen)
"""


def _gen_bathtub(x, y, style):
    """Ванна."""
    return f"""
# ═══ Bathtub ═══
# Outer shell
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.3))
tub = bpy.context.active_object; tub.name = "Bathtub"
tub.scale = (0.85, 0.4, 0.3)
bpy.ops.object.transform_apply(scale=True)
tub.data.materials.append(mat_white)
# Inner (slightly smaller, to create rim effect)
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.32))
inner = bpy.context.active_object; inner.name = "Bathtub_Inner"
inner.scale = (0.78, 0.35, 0.28)
bpy.ops.object.transform_apply(scale=True)
mat_water = bpy.data.materials.new("Water_Bath")
mat_water.use_nodes = True
bsdf = mat_water.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.7, 0.85, 0.95, 1.0)
    bsdf.inputs["Alpha"].default_value = 0.5
inner.data.materials.append(mat_water)
# Faucet
bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=0.3, location=({x} + 0.7, {y}, 0.6))
faucet = bpy.context.active_object; faucet.name = "Faucet"
faucet.data.materials.append(mat_metal_furn)
"""


def _gen_toilet(x, y, style):
    """Унитаз."""
    return f"""
# ═══ Toilet ═══
# Base
bpy.ops.mesh.primitive_cylinder_add(radius=0.2, depth=0.4, location=({x}, {y}, 0.2))
base = bpy.context.active_object; base.name = "Toilet_Base"
base.data.materials.append(mat_white)
# Bowl
bpy.ops.mesh.primitive_cylinder_add(radius=0.18, depth=0.15, location=({x}, {y}, 0.42))
bowl = bpy.context.active_object; bowl.name = "Toilet_Bowl"
bowl.data.materials.append(mat_white)
# Tank
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y} + 0.2, 0.45))
tank = bpy.context.active_object; tank.name = "Toilet_Tank"
tank.scale = (0.18, 0.08, 0.2)
bpy.ops.object.transform_apply(scale=True)
tank.data.materials.append(mat_white)
# Lid
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.5))
lid = bpy.context.active_object; lid.name = "Toilet_Lid"
lid.scale = (0.18, 0.2, 0.02)
bpy.ops.object.transform_apply(scale=True)
lid.data.materials.append(mat_white)
"""


def _gen_sink(x, y, style):
    """Умывальник."""
    return f"""
# ═══ Sink ═══
# Pedestal
bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=0.6, location=({x}, {y}, 0.3))
ped = bpy.context.active_object; ped.name = "Sink_Pedestal"
ped.data.materials.append(mat_white)
# Basin
bpy.ops.mesh.primitive_cylinder_add(radius=0.25, depth=0.1, location=({x}, {y}, 0.62))
basin = bpy.context.active_object; basin.name = "Sink_Basin"
basin.data.materials.append(mat_white)
# Faucet
bpy.ops.mesh.primitive_cylinder_add(radius=0.015, depth=0.2, location=({x}, {y} - 0.1, 0.75))
faucet = bpy.context.active_object; faucet.name = "Sink_Faucet"
faucet.data.materials.append(mat_metal_furn)
"""


def _gen_refrigerator(x, y, style):
    """Холодильник."""
    return f"""
# ═══ Refrigerator ═══
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.9))
fridge = bpy.context.active_object; fridge.name = "Refrigerator"
fridge.scale = (0.35, 0.35, 0.9)
bpy.ops.object.transform_apply(scale=True)
fridge.data.materials.append(mat_white)
# Handle
bpy.ops.mesh.primitive_cylinder_add(radius=0.01, depth=0.5, location=({x} - 0.36, {y}, 0.9))
handle = bpy.context.active_object; handle.name = "Fridge_Handle"
handle.data.materials.append(mat_metal_furn)
"""


def _gen_stove(x, y, style):
    """Плита."""
    return f"""
# ═══ Stove ═══
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.43))
stove = bpy.context.active_object; stove.name = "Stove"
stove.scale = (0.3, 0.3, 0.43)
bpy.ops.object.transform_apply(scale=True)
stove.data.materials.append(mat_metal_furn)
# Burners
for bx, by in [(-0.1, -0.1), (-0.1, 0.1), (0.1, -0.1), (0.1, 0.1)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.06, depth=0.01, location=({x} + bx, {y} + by, 0.87))
    burner = bpy.context.active_object; burner.name = "Burner"
    mat_burner = bpy.data.materials.new("Burner_Material")
    mat_burner.use_nodes = True
    bsdf = mat_burner.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.1, 0.1, 0.1, 1.0)
        bsdf.inputs["Metallic"].default_value = 0.9
    burner.data.materials.append(mat_burner)
"""


def _gen_chandelier(x, y, style):
    """Люстра."""
    return f"""
# ═══ Chandelier ═══
bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=0.5, location=({x}, {y}, 2.75))
rod = bpy.context.active_object; rod.name = "Chandelier_Rod"
rod.data.materials.append(mat_metal_furn)
bpy.ops.mesh.primitive_cylinder_add(radius=0.25, depth=0.05, location=({x}, {y}, 2.5))
base = bpy.context.active_object; base.name = "Chandelier_Base"
base.data.materials.append(mat_metal_furn)
for angle in range(0, 360, 60):
    import math
    lx = {x} + 0.2 * math.cos(math.radians(angle))
    ly = {y} + 0.2 * math.sin(math.radians(angle))
    bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.08, location=(lx, ly, 2.45))
    lamp = bpy.context.active_object; lamp.name = "Chandelier_Lamp"
    mat_lamp = bpy.data.materials.new("Lamp_Light")
    mat_lamp.use_nodes = True
    bsdf = mat_lamp.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (1.0, 0.95, 0.8, 1.0)
        bsdf.inputs["Emission Color"].default_value = (1.0, 0.95, 0.8, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 2.0
    lamp.data.materials.append(mat_lamp)
"""


def _gen_tv_stand(x, y, style):
    """ТВ-тумба."""
    return f"""
# ═══ TV Stand ═══
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.25))
stand = bpy.context.active_object; stand.name = "TV_Stand"
stand.scale = (0.75, 0.2, 0.25)
bpy.ops.object.transform_apply(scale=True)
stand.data.materials.append(mat_wood_furn)
# TV
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.7))
tv = bpy.context.active_object; tv.name = "TV"
tv.scale = (0.6, 0.02, 0.35)
bpy.ops.object.transform_apply(scale=True)
tv.data.materials.append(mat_metal_furn)
"""


def _gen_coffee_table(x, y, style):
    """Журнальный столик."""
    return f"""
# ═══ Coffee Table ═══
bpy.ops.mesh.primitive_cylinder_add(radius=0.35, depth=0.03, location=({x}, {y}, 0.4))
top = bpy.context.active_object; top.name = "CoffeeTable_Top"
top.data.materials.append(mat_glass_furn)
for angle in range(0, 360, 90):
    import math
    lx = {x} + 0.25 * math.cos(math.radians(angle))
    ly = {y} + 0.25 * math.sin(math.radians(angle))
    bpy.ops.mesh.primitive_cylinder_add(radius=0.015, depth=0.39, location=(lx, ly, 0.195))
    leg = bpy.context.active_object; leg.name = "CoffeeTable_Leg"
    leg.data.materials.append(mat_metal_furn)
"""


def _gen_nightstand(x, y, style):
    """Прикроватная тумба."""
    return f"""
# ═══ Nightstand ═══
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 0.27))
ns = bpy.context.active_object; ns.name = "Nightstand"
ns.scale = (0.25, 0.2, 0.27)
bpy.ops.object.transform_apply(scale=True)
ns.data.materials.append(mat_wood_furn)
# Drawer handle
bpy.ops.mesh.primitive_cylinder_add(radius=0.008, depth=0.06, location=({x}, {y} - 0.21, 0.27))
handle = bpy.context.active_object; handle.name = "Nightstand_Handle"
handle.rotation_euler[1] = math.radians(90)
handle.data.materials.append(mat_metal_furn)
# Lamp on top
bpy.ops.mesh.primitive_cylinder_add(radius=0.01, depth=0.2, location=({x}, {y}, 0.64))
lamp_base = bpy.context.active_object; lamp_base.name = "TableLamp_Base"
lamp_base.data.materials.append(mat_metal_furn)
bpy.ops.mesh.primitive_cone_add(radius1=0.08, radius2=0.03, depth=0.12, location=({x}, {y}, 0.8))
shade = bpy.context.active_object; shade.name = "TableLamp_Shade"
shade.data.materials.append(mat_fabric)
"""


# Registry (AFTER all function definitions)
FURNITURE_GENERATORS = {
    "sofa": _gen_sofa,
    "диван": _gen_sofa,
    "table": _gen_table,
    "стол": _gen_table,
    "bed": _gen_bed,
    "кровать": _gen_bed,
    "кровать_двуспальная": _gen_bed,
    "chair": _gen_chair,
    "стул": _gen_chair,
    "wardrobe": _gen_wardrobe,
    "шкаф": _gen_wardrobe,
    "шкаф_купе": _gen_wardrobe,
    "bookshelf": _gen_bookshelf,
    "стеллаж": _gen_bookshelf,
    "книжный_стеллаж": _gen_bookshelf,
    "desk": _gen_desk,
    "стол_рабочий": _gen_desk,
    "рабочий_стол": _gen_desk,
    "bathtub": _gen_bathtub,
    "ванна": _gen_bathtub,
    "toilet": _gen_toilet,
    "унитаз": _gen_toilet,
    "sink": _gen_sink,
    "умывальник": _gen_sink,
    "refrigerator": _gen_refrigerator,
    "холодильник": _gen_refrigerator,
    "stove": _gen_stove,
    "плита": _gen_stove,
    "chandelier": _gen_chandelier,
    "люстра": _gen_chandelier,
    "tv_stand": _gen_tv_stand,
    "тв_тумба": _gen_tv_stand,
    "coffee_table": _gen_coffee_table,
    "журнальный_столик": _gen_coffee_table,
    "nightstand": _gen_nightstand,
    "прикроватная_тумба": _gen_nightstand,
}
