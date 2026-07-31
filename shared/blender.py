"""
shared/blender.py — единый модуль генерации bpy-скриптов для Blender.

Улучшения по сравнению с оригиналом:
- Текстурированные материалы (PBR)
- Окна с рамами и подоконниками
- Лестницы между этажами
- Водосточные трубы
- Карнизы
- Улучшенное освещение
- Проверка returncode Blender
"""

import os
import uuid
import subprocess

from shared.config import settings
from shared.validation import safe_val


# ═══════════════════════════════════════════════════════════════
# MATERIAL HELPERS
# ═══════════════════════════════════════════════════════════════

def _make_mat_code(name: str, color: tuple, roughness: float = 0.8,
                   metallic: float = 0.0, emission: float = 0.0) -> str:
    """Генерирует код создания PBR-материала."""
    r, g, b = color
    code = f"""
mat_{name}=bpy.data.materials.new("{name}")
mat_{name}.use_nodes=True
bsdf_{name}=mat_{name}.node_tree.nodes.get("Principled BSDF")
if bsdf_{name}:
    bsdf_{name}.inputs["Base Color"].default_value=({r},{g},{b},1.0)
    bsdf_{name}.inputs["Roughness"].default_value={roughness}
    bsdf_{name}.inputs["Metallic"].default_value={metallic}
"""
    if emission > 0:
        code += f"""    try:bsdf_{name}.inputs["Emission Color"].default_value=({r},{g},{b},1.0)
    except:pass
    try:bsdf_{name}.inputs["Emission Strength"].default_value={emission}
    except:pass
"""
    return code


# ═══════════════════════════════════════════════════════════════
# WINDOW GENERATOR
# ═══════════════════════════════════════════════════════════════

def _window_code(x: str, z: str, floor: str, idx: str,
                 wall_y: str, thick: str) -> str:
    """Генерирует окно с рамой, стеклом и подоконником (8-space indent для вставки в цикл)."""
    return f"""
        # Window {{floor}}_{{idx}}
        bpy.ops.mesh.primitive_cube_add(size=1,location=({x},{wall_y},{z}))
        wf=bpy.context.active_object;wf.name=f"WindowFrame_{{floor}}_{{idx}}"
        wf.scale=(1.3,0.06,1.6);bpy.ops.object.transform_apply(scale=True)
        wf.data.materials.append(mat_frame)
        bpy.ops.mesh.primitive_cube_add(size=1,location=({x},{wall_y},{z}))
        wg=bpy.context.active_object;wg.name=f"WindowGlass_{{floor}}_{{idx}}"
        wg.scale=(1.1,0.02,1.4);bpy.ops.object.transform_apply(scale=True)
        wg.data.materials.append(mat_glass)
        bpy.ops.mesh.primitive_cube_add(size=1,location=({x},{wall_y},{z}-0.85))
        ws=bpy.context.active_object;ws.name=f"WindowSill_{{floor}}_{{idx}}"
        ws.scale=(1.4,0.12,0.05);bpy.ops.object.transform_apply(scale=True)
        ws.data.materials.append(mat_concrete)
"""


# ═══════════════════════════════════════════════════════════════
# STAIRCASE GENERATOR
# ═══════════════════════════════════════════════════════════════

def _staircase_code(W: str, L: str, fH: str, floors: str) -> str:
    """Генерирует лестницу между этажами."""
    return f"""
# Staircase
steps_n=12
step_h={fH}/steps_n
step_d=0.25
for s in range(steps_n):
    bpy.ops.mesh.primitive_cube_add(size=1,location=({W}/2-0.6,-{L}/2+0.3+s*step_d,s*step_h+step_h/2))
    st=bpy.context.active_object;st.name=f"Step_{{s}}"
    st.scale=(0.5,step_d/2,step_h/2)
    bpy.ops.object.transform_apply(scale=True)
    st.data.materials.append(mat_concrete)
# Railing
bpy.ops.mesh.primitive_cylinder_add(radius=0.02,depth={fH},location=({W}/2-0.35,-{L}/2+0.15,{fH}/2))
sr=bpy.context.active_object;sr.name="StairRailing_L"
sr.data.materials.append(mat_railing)
bpy.ops.mesh.primitive_cylinder_add(radius=0.02,depth={fH},location=({W}/2-0.85,-{L}/2+0.15,{fH}/2))
sr2=bpy.context.active_object;sr2.name="StairRailing_R"
sr2.data.materials.append(mat_railing)
for s in range(4):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.015,depth=0.8,location=({W}/2-0.35,-{L}/2+0.15+s*0.8,{fH}/2))
    vb=bpy.context.active_object;vb.name=f"Baluster_{{s}}"
    vb.data.materials.append(mat_railing)
"""


# ═══════════════════════════════════════════════════════════════
# DOWNSPOUT / GUTTER GENERATOR
# ═══════════════════════════════════════════════════════════════

def _downspout_code(W: str, L: str, total_h: str) -> str:
    """Генерирует водосточные трубы."""
    return f"""
# Downspouts
for dx,dy in [(-{W}/2-0.15,-{L}/2-0.15),({W}/2+0.15,-{L}/2-0.15),(-{W}/2-0.15,{L}/2+0.15),({W}/2+0.15,{L}/2+0.15)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.04,depth={total_h},location=(dx,dy,{total_h}/2))
    ds=bpy.context.active_object;ds.name="Downspout"
    ds.data.materials.append(mat_railing)
"""


# ═══════════════════════════════════════════════════════════════
# BUILDING GENERATOR
# ═══════════════════════════════════════════════════════════════

def generate_bpy_script(params: dict) -> str:
    """
    Генерирует bpy-скрипт для здания.
    Улучшенная версия: текстуры, окна с рамами, лестницы, водостоки.
    """
    W = safe_val(params.get("width"), 10, range(1, 201))
    L = safe_val(params.get("length"), 12, range(1, 201))
    floors = safe_val(params.get("floors"), 2, range(1, 21))
    fH = safe_val(params.get("floor_height"), 3.0)
    thick = safe_val(params.get("wall_thickness"), 0.3)
    roof_type = safe_val(params.get("roof_type"), "gabled", ["gabled", "flat", "hip"])
    mat = safe_val(
        params.get("facade_material"), "plaster",
        ["brick", "wood", "glass", "stone", "concrete", "plaster"],
    )
    has_balcony = bool(params.get("has_balcony", False))
    has_terrace = bool(params.get("has_terrace", False))
    has_garage = bool(params.get("has_garage", False))

    colors = {
        "brick": (0.71, 0.40, 0.12), "wood": (0.55, 0.41, 0.13),
        "glass": (0.53, 0.81, 0.92), "plaster": (0.91, 0.88, 0.83),
        "stone": (0.50, 0.50, 0.50), "concrete": (0.63, 0.63, 0.63),
    }
    wr, wg, wb = colors.get(mat, (0.91, 0.88, 0.83))
    total_h = floors * fH

    # === Header ===
    script = f"""import bpy, os, math
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
W={W};L={L};floors={floors};fH={fH};thick={thick};total_h=floors*fH
"""

    # === Materials (PBR) ===
    script += _make_mat_code("wall", (wr, wg, wb), 0.85)
    script += _make_mat_code("roof", (0.545, 0.271, 0.075), 0.7)
    script += _make_mat_code("glass", (0.8, 0.9, 1.0), 0.05, 0.1)
    script += _make_mat_code("ground", (0.29, 0.49, 0.25), 0.95)
    script += _make_mat_code("concrete", (0.5, 0.5, 0.5), 0.95)
    script += _make_mat_code("door", (0.29, 0.22, 0.16), 0.7)
    script += _make_mat_code("frame", (0.85, 0.85, 0.85), 0.4, 0.1)
    script += _make_mat_code("railing", (0.2, 0.2, 0.2), 0.3, 0.8)

    # === Foundation ===
    script += f"""
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,-0.15))
fnd=bpy.context.active_object;fnd.name="Foundation"
fnd.scale=(W/2+0.3,L/2+0.3,0.15)
bpy.ops.object.transform_apply(scale=True);fnd.data.materials.append(mat_concrete)
"""

    # === Walls + Windows per floor ===
    script += f"""
for floor in range(floors):
    z=floor*fH+fH/2
    for side,(sx,sy) in [("F",(0,-L/2)),("B",(0,L/2)),("L",(-W/2,0)),("R",(W/2,0))]:
        is_x=side in ("L","R")
        bpy.ops.mesh.primitive_cube_add(size=1,location=(sx,sy,z))
        w=bpy.context.active_object;w.name=f"Wall_{{side}}_{{floor}}"
        w.scale=((thick if is_x else W)/2,(L if is_x else thick)/2,fH/2)
        bpy.ops.object.transform_apply(scale=True);w.data.materials.append(mat_wall)
"""

    # Windows (front and back walls only, with frames)
    script += f"""
    n_win=max(2,W//3)
    for i in range(n_win):
        x=-W/2+(i+1)*W/(n_win+1)
        wz=floor*fH+fH*0.4
"""
    script += _window_code("x", "wz", "floor", "i", f"-L/2-thick/2-0.01", "thick")
    script += _window_code("x", "wz", "floor", "i", f"L/2+thick/2+0.01", "thick")

    # === Floor slabs ===
    script += f"""
    if floor>0:
        bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,floor*fH))
        slab=bpy.context.active_object;slab.name=f"Slab_{{floor}}"
        slab.scale=(W/2,L/2,0.1)
        bpy.ops.object.transform_apply(scale=True);slab.data.materials.append(mat_concrete)
"""

    # === Staircase (if multi-floor) ===
    if floors > 1:
        script += _staircase_code("W", "L", "fH", "floors")

    # === Roof ===
    script += f"""
rh=2.5
if "{roof_type}"=="gabled":
    verts=[(-W/2-0.3,-L/2-0.3,total_h),(W/2+0.3,-L/2-0.3,total_h),
           (W/2+0.3,L/2+0.3,total_h),(-W/2-0.3,L/2+0.3,total_h),
           (0,-L/2-0.3,total_h+rh),(0,L/2+0.3,total_h+rh)]
    faces=[(0,1,4),(2,3,5),(0,3,5,4),(1,2,5,4)]
    mesh=bpy.data.meshes.new("RoofMesh");mesh.from_pydata(verts,[],faces);mesh.update()
    roof=bpy.data.objects.new("Roof",mesh);bpy.context.collection.objects.link(roof)
    roof.data.materials.append(mat_roof)
elif "{roof_type}"=="flat":
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,total_h+0.1))
    roof=bpy.context.active_object;roof.name="Roof"
    roof.scale=(W/2+0.3,L/2+0.3,0.1)
    bpy.ops.object.transform_apply(scale=True);roof.data.materials.append(mat_roof)
elif "{roof_type}"=="hip":
    verts=[(-W/2-0.3,-L/2-0.3,total_h),(W/2+0.3,-L/2-0.3,total_h),
           (W/2+0.3,L/2+0.3,total_h),(-W/2-0.3,L/2+0.3,total_h),
           (0,0,total_h+rh)]
    faces=[(0,1,4),(1,2,4),(2,3,4),(3,0,4)]
    mesh=bpy.data.meshes.new("RoofMesh");mesh.from_pydata(verts,[],faces);mesh.update()
    roof=bpy.data.objects.new("Roof",mesh);bpy.context.collection.objects.link(roof)
    roof.data.materials.append(mat_roof)
"""

    # === Dormer windows (мансардные окна), Bay window, Cornices, Quoins ===
    script += f"""
# Dormer windows for gabled roof
if "{roof_type}"=="gabled" and floors >= 2:
    n_dormers = max(1, W // 4)
    for di in range(n_dormers):
        dx = -W/2 + (di+1)*W/(n_dormers+1)
        for dz,side in [(-L/2-0.1,"F"),(L/2+0.1,"B")]:
            bpy.ops.mesh.primitive_cube_add(size=1,location=(dx,dz,total_h+0.8))
            dormer=bpy.context.active_object;dormer.name=f"Dormer_{{side}}_{{di}}"
            dormer.scale=(0.6,0.4,0.5);bpy.ops.object.transform_apply(scale=True)
            dormer.data.materials.append(mat_wall)
            bpy.ops.mesh.primitive_cube_add(size=1,location=(dx,dz,total_h+1.15))
            droof=bpy.context.active_object;droof.name=f"DRoof_{{side}}_{{di}}"
            droof.scale=(0.7,0.5,0.05);bpy.ops.object.transform_apply(scale=True)
            droof.data.materials.append(mat_roof)
            bpy.ops.mesh.primitive_cube_add(size=1,location=(dx,dz-0.2,total_h+0.7))
            dw=bpy.context.active_object;dw.name=f"DWin_{{side}}_{{di}}"
            dw.scale=(0.4,0.02,0.35);bpy.ops.object.transform_apply(scale=True)
            dw.data.materials.append(mat_glass)

# Bay window on front wall
if floors >= 2:
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2-0.6,fH*0.45))
    bay=bpy.context.active_object;bay.name="BayWindow"
    bay.scale=(2.2,0.6,0.9);bpy.ops.object.transform_apply(scale=True)
    bay.data.materials.append(mat_wall)
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2-0.6,fH*0.95))
    bayroof=bpy.context.active_object;bayroof.name="BayRoof"
    bayroof.scale=(2.4,0.7,0.04);bpy.ops.object.transform_apply(scale=True)
    bayroof.data.materials.append(mat_roof)
    for pi,px in enumerate([-0.7,0,0.7]):
        bpy.ops.mesh.primitive_cube_add(size=1,location=(px,-L/2-0.85,fH*0.45))
        bg=bpy.context.active_object;bg.name=f"BayGlass_{{pi}}"
        bg.scale=(0.5,0.02,0.7);bpy.ops.object.transform_apply(scale=True)
        bg.data.materials.append(mat_glass)

# Detailed cornice at roof line
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,total_h+0.05))
cornice_top=bpy.context.active_object;cornice_top.name="CorniceTop"
cornice_top.scale=(W/2+0.5,L/2+0.5,0.08);bpy.ops.object.transform_apply(scale=True)
cornice_top.data.materials.append(mat_concrete)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,total_h-0.15))
cornice_bot=bpy.context.active_object;cornice_bot.name="CorniceBot"
cornice_bot.scale=(W/2+0.45,L/2+0.45,0.04);bpy.ops.object.transform_apply(scale=True)
cornice_bot.data.materials.append(mat_concrete)

# Quoins at corners
for cx,cy in [(-W/2,-L/2),(W/2,-L/2),(-W/2,L/2),(W/2,L/2)]:
    for qi in range(floors):
        qz=qi*fH+fH/2
        bpy.ops.mesh.primitive_cube_add(size=1,location=(cx,cy,qz))
        quo=bpy.context.active_object;quo.name=f"Quoin_{{qi}}"
        quo.scale=(0.25,0.25,fH/2-0.05);bpy.ops.object.transform_apply(scale=True)
        quo.data.materials.append(mat_concrete)
"""

    # === Door ===
    script += f"""
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2-thick/2-0.01,1.1))
door=bpy.context.active_object;door.name="Door";door.scale=(0.5,0.04,1.1)
door.data.materials.append(mat_door)
"""

    # === Downspouts ===
    script += _downspout_code("W", "L", "total_h")

    # === Balcony ===
    if has_balcony:
        script += """
for floor in range(1,floors):
    z=floor*fH
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2-1.5,z+0.05))
    balc=bpy.context.active_object;balc.name=f"Balcony_{floor}"
    balc.scale=(1.5,0.75,0.05);bpy.ops.object.transform_apply(scale=True)
    balc.data.materials.append(mat_concrete)
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2-2.2,z+0.6))
    rail=bpy.context.active_object;rail.name=f"Railing_{floor}"
    rail.scale=(1.5,0.03,0.5);bpy.ops.object.transform_apply(scale=True)
    rail.data.materials.append(mat_railing)
"""

    # === Terrace ===
    if has_terrace:
        script += """
bpy.ops.mesh.primitive_cube_add(size=1,location=(W/2+2,0,0.05))
terr=bpy.context.active_object;terr.name="Terrace"
terr.scale=(1.5,L/2,0.05);bpy.ops.object.transform_apply(scale=True)
terr.data.materials.append(mat_concrete)
"""

    # === Garage ===
    if has_garage:
        script += """
bpy.ops.mesh.primitive_cube_add(size=1,location=(-W/2-3,0,1.5))
garage=bpy.context.active_object;garage.name="Garage"
garage.scale=(2,2.5,1.5);bpy.ops.object.transform_apply(scale=True)
garage.data.materials.append(mat_wall)
bpy.ops.mesh.primitive_cube_add(size=1,location=(-W/2-3,-2.5,1.2))
gd=bpy.context.active_object;gd.name="GarageDoor"
gd.scale=(1.75,0.04,1.2);bpy.ops.object.transform_apply(scale=True)
gd.data.materials.append(mat_door)
"""

    # === Ground + Camera + Lighting ===
    script += f"""
bpy.ops.mesh.primitive_plane_add(size=50,location=(0,0,-0.01))
gnd=bpy.context.active_object;gnd.name="Ground";gnd.data.materials.append(mat_ground)

cam=bpy.data.cameras.new("Camera");cam.lens=35
cam_obj=bpy.data.objects.new("Camera",cam)
bpy.context.scene.collection.objects.link(cam_obj);bpy.context.scene.camera=cam_obj
cam_obj.location=(W*1.5,-L*1.5,total_h*1.2)
cam_obj.rotation_euler=(math.radians(60),0,math.radians(45))

# Camera clip
for c in bpy.data.cameras:
    c.clip_start=0.1
    c.clip_end=1000

sun=bpy.data.lights.new("Sun","SUN");sun.energy=4;sun.color=(1.0,0.95,0.9)
sun_obj=bpy.data.objects.new("Sun",sun)
bpy.context.collection.objects.link(sun_obj)
sun_obj.rotation_euler=(math.radians(45),math.radians(15),math.radians(30))

fill=bpy.data.lights.new("Fill","AREA");fill.energy=200;fill.size=10
fill_obj=bpy.data.objects.new("FillLight",fill)
bpy.context.collection.objects.link(fill_obj)
fill_obj.location=(-W*1.5,L*1.5,total_h)
fill_obj.rotation_euler=(math.radians(60),0,math.radians(-135))

world=bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world=world;world.use_nodes=True
bg=world.node_tree.nodes.get("Background")
if bg:bg.inputs["Color"].default_value=(0.5,0.7,1.0,1.0);bg.inputs["Strength"].default_value=1.2
"""

    return script


# ═══════════════════════════════════════════════════════════════
# INTERIOR GENERATOR
# ═══════════════════════════════════════════════════════════════

def generate_interior_script(params: dict) -> str:
    """
    Генерирует bpy-скрипт для интерьера.
    Улучшенная версия: текстуры, плинтусы, карнизы, базовая мебель.
    """
    w = params.get("width", 6)
    l = params.get("length", 8)
    h = params.get("height", 3)
    style = params.get("style", "modern")
    furniture = params.get("furniture", ["sofa", "table", "chandelier"])

    style_colors = {
        "modern":       {"wall": (0.96, 0.96, 0.96), "floor": (0.77, 0.66, 0.51), "accent": (0.17, 0.24, 0.31)},
        "classic":      {"wall": (0.94, 0.90, 0.83), "floor": (0.55, 0.41, 0.08), "accent": (0.55, 0.0, 0.0)},
        "scandinavian": {"wall": (0.98, 0.98, 0.98), "floor": (0.83, 0.72, 0.59), "accent": (0.56, 0.74, 0.56)},
        "loft":         {"wall": (0.63, 0.63, 0.63), "floor": (0.42, 0.42, 0.42), "accent": (1.0, 0.42, 0.21)},
        "minimalist":   {"wall": (1.0, 1.0, 1.0), "floor": (0.88, 0.85, 0.80), "accent": (0.0, 0.0, 0.0)},
        "hitech":       {"wall": (0.9, 0.9, 0.95), "floor": (0.3, 0.3, 0.35), "accent": (0.0, 0.6, 0.8)},
    }
    sc = style_colors.get(style, style_colors["modern"])

    # === Header ===
    script = f"""import bpy, math
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
W={w};L={l};H={h}
"""

    # === Materials ===
    script += _make_mat_code("wall", sc["wall"], 0.9)
    script += _make_mat_code("floor", sc["floor"], 0.6)
    script += _make_mat_code("ceiling", (1, 1, 1), 0.95)
    script += _make_mat_code("accent", sc["accent"], 0.7)
    script += _make_mat_code("baseboard", (0.9, 0.9, 0.9), 0.5)
    script += _make_mat_code("crown", (0.95, 0.95, 0.95), 0.4)

    # === Floor + Ceiling ===
    script += f"""
bpy.ops.mesh.primitive_plane_add(size=1,location=(0,0,0))
fl=bpy.context.active_object;fl.name="Floor";fl.scale=(W/2,L/2,1)
bpy.ops.object.transform_apply(scale=True);fl.data.materials.append(mat_floor)

bpy.ops.mesh.primitive_plane_add(size=1,location=(0,0,H))
ceil=bpy.context.active_object;ceil.name="Ceiling";ceil.scale=(W/2,L/2,1)
ceil.rotation_euler.x=math.pi
bpy.ops.object.transform_apply(scale=True,rotation=True);ceil.data.materials.append(mat_ceiling)
"""

    # === Walls ===
    script += """
for name,(sx,sy),(dx,dy) in [("Front",(0,-L/2),(W,0.15)),("Back",(0,L/2),(W,0.15)),
                               ("Left",(-W/2,0),(0.15,L)),("Right",(W/2,0),(0.15,L))]:
    bpy.ops.mesh.primitive_cube_add(size=1,location=(sx,sy,H/2))
    wall=bpy.context.active_object;wall.name=name;wall.scale=(dx/2,dy/2,H/2)
    bpy.ops.object.transform_apply(scale=True);wall.data.materials.append(mat_wall)
"""

    # === Baseboards ===
    script += """
# Baseboards
bh=0.08
for name,(sx,sy),(dx,dy) in [("BaseFront",(0,-L/2+0.08),(W-0.1,bh)),("BaseBack",(0,L/2-0.08),(W-0.1,bh)),
                                ("BaseLeft",(-W/2+0.08,0),(bh,L-0.1)),("BaseRight",(W/2-0.08,0),(bh,L-0.1))]:
    bpy.ops.mesh.primitive_cube_add(size=1,location=(sx,sy,bh/2))
    bb=bpy.context.active_object;bb.name=name;bb.scale=(dx/2,dy/2,bh/2)
    bpy.ops.object.transform_apply(scale=True);bb.data.materials.append(mat_baseboard)
"""

    # === Crown molding ===
    script += """
# Crown molding
ch=0.06
for name,(sx,sy),(dx,dy) in [("CrownFront",(0,-L/2+0.07),(W-0.05,ch)),("CrownBack",(0,L/2-0.07),(W-0.05,ch)),
                                ("CrownLeft",(-W/2+0.07,0),(ch,L-0.05)),("CrownRight",(W/2-0.07,0),(ch,L-0.05))]:
    bpy.ops.mesh.primitive_cube_add(size=1,location=(sx,sy,H-ch/2))
    cm=bpy.context.active_object;cm.name=name;cm.scale=(dx/2,dy/2,ch/2)
    bpy.ops.object.transform_apply(scale=True);cm.data.materials.append(mat_crown)
"""

    # === Furniture ===
    furniture_scripts = {
        "sofa": """
# Sofa
sofa_mat=make_mat("Sofa",(0.29,0.29,0.29),0.85)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2+1,0.3))
seat=bpy.context.active_object;seat.name="Sofa_Seat";seat.scale=(1,0.5,0.3)
bpy.ops.object.transform_apply(scale=True);seat.data.materials.append(sofa_mat)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2+1.35,0.65))
back=bpy.context.active_object;back.name="Sofa_Back";back.scale=(1,0.1,0.35)
bpy.ops.object.transform_apply(scale=True);back.data.materials.append(sofa_mat)
""",
        "table": """
# Table
table_mat=make_mat("Table",(0.55,0.41,0.08),0.6)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,0.75))
top=bpy.context.active_object;top.name="Table_Top";top.scale=(0.6,0.4,0.04)
bpy.ops.object.transform_apply(scale=True);top.data.materials.append(table_mat)
for dx,dy in [(-1,-1),(1,-1),(-1,1),(1,1)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.03,depth=0.75,location=(dx*0.5,dy*0.3,0.375))
    leg=bpy.context.active_object;leg.name="Table_Leg";leg.data.materials.append(table_mat)
""",
        "bed": """
# Bed
bed_mat=make_mat("Bed",(0.94,0.94,0.94),0.9)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,0.25))
mattress=bpy.context.active_object;mattress.name="Mattress";mattress.scale=(0.9,1,0.25)
bpy.ops.object.transform_apply(scale=True);mattress.data.materials.append(bed_mat)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0.95,0.6))
hb=bpy.context.active_object;hb.name="Headboard";hb.scale=(0.9,0.05,0.6)
hb.data.materials.append(make_mat("Headboard",(0.24,0.17,0.12),0.7))
""",
        "chandelier": """
# Chandelier
bpy.ops.mesh.primitive_cylinder_add(radius=0.01,depth=1,location=(0,0,H-0.5))
wire=bpy.context.active_object;wire.name="Wire"
wire.data.materials.append(make_mat("Metal",(0.2,0.2,0.2),0.3,0.8))
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2,location=(0,0,H-1))
shade=bpy.context.active_object;shade.name="Shade"
shade.data.materials.append(make_mat("Light",(1,0.96,0.88),0.5,5.0))
light_data=bpy.data.lights.new("Chandelier","POINT");light_data.energy=500;light_data.color=(1.0,0.95,0.85)
light_obj=bpy.data.objects.new("Chandelier",light_data)
bpy.context.collection.objects.link(light_obj);light_obj.location=(0,0,H-1)
""",
        "desk": """
# Desk
desk_mat=make_mat("Desk",(0.6,0.45,0.25),0.65)
bpy.ops.mesh.primitive_cube_add(size=1,location=(L/2-1,0,0.75))
dtop=bpy.context.active_object;dtop.name="Desk_Top";dtop.scale=(0.5,0.8,0.03)
bpy.ops.object.transform_apply(scale=True);dtop.data.materials.append(desk_mat)
for dx,dy in [(-1,-1),(1,-1),(-1,1),(1,1)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.025,depth=0.75,location=(L/2-1+dx*0.45,dy*0.7,0.375))
    dleg=bpy.context.active_object;dleg.name="Desk_Leg";dleg.data.materials.append(desk_mat)
""",
        "wardrobe": """
# Wardrobe
ward_mat=make_mat("Wardrobe",(0.45,0.32,0.18),0.7)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,L/2-0.5,0.9))
ward=bpy.context.active_object;ward.name="Wardrobe";ward.scale=(0.8,0.4,0.9)
bpy.ops.object.transform_apply(scale=True);ward.data.materials.append(ward_mat)
""",
        "nightstand": """
# Nightstand
ns_mat=make_mat("Nightstand",(0.5,0.38,0.22),0.7)
bpy.ops.mesh.primitive_cube_add(size=1,location=(-1.2,0.5,0.25))
ns=bpy.context.active_object;ns.name="Nightstand";ns.scale=(0.25,0.25,0.25)
bpy.ops.object.transform_apply(scale=True);ns.data.materials.append(ns_mat)
""",
        "bookshelf": """
# Bookshelf
shelf_mat=make_mat("Bookshelf",(0.5,0.35,0.2),0.7)
for i in range(3):
    bpy.ops.mesh.primitive_cube_add(size=1,location=(-W/2+0.2,L/2-0.3,0.4+i*0.5))
    sh=bpy.context.active_object;sh.name=f"Shelf_{i}";sh.scale=(0.15,0.25,0.02)
    bpy.ops.object.transform_apply(scale=True);sh.data.materials.append(shelf_mat)
""",
        "sink": """
# Sink
sink_mat=make_mat("Sink",(0.9,0.9,0.9),0.3,0.1)
bpy.ops.mesh.primitive_cylinder_add(radius=0.2,depth=0.15,location=(-W/2+0.5,0,0.9))
sn=bpy.context.active_object;sn.name="Sink";sn.data.materials.append(sink_mat)
""",
        "stove": """
# Stove
stove_mat=make_mat("Stove",(0.2,0.2,0.2),0.5,0.3)
bpy.ops.mesh.primitive_cube_add(size=1,location=(-W/2+0.5,L/2-0.5,0.45))
stv=bpy.context.active_object;stv.name="Stove";stv.scale=(0.3,0.3,0.45)
bpy.ops.object.transform_apply(scale=True);stv.data.materials.append(stove_mat)
""",
        "bathtub": """
# Bathtub
tub_mat=make_mat("Bathtub",(0.95,0.95,0.95),0.2)
bpy.ops.mesh.primitive_cylinder_add(radius=0.5,depth=0.4,location=(L/2-1,0,0.2))
tub=bpy.context.active_object;tub.name="Bathtub";tub.data.materials.append(tub_mat)
""",
        "chair": """
# Chair
chair_mat=make_mat("Chair",(0.3,0.3,0.3),0.8)
bpy.ops.mesh.primitive_cube_add(size=1,location=(L/2-1,0.8,0.45))
chseat=bpy.context.active_object;chseat.name="Chair_Seat";chseat.scale=(0.2,0.2,0.03)
bpy.ops.object.transform_apply(scale=True);chseat.data.materials.append(chair_mat)
bpy.ops.mesh.primitive_cube_add(size=1,location=(L/2-1,0.8,0.7))
chback=bpy.context.active_object;chback.name="Chair_Back";chback.scale=(0.2,0.03,0.25)
bpy.ops.object.transform_apply(scale=True);chback.data.materials.append(chair_mat)
""",
    }

    for item in furniture:
        if item in furniture_scripts:
            script += furniture_scripts[item]

    # === Camera + Lighting ===
    script += f"""
cam=bpy.data.cameras.new("InteriorCam");cam.lens=24
cam_obj=bpy.data.objects.new("InteriorCam",cam)
bpy.context.scene.collection.objects.link(cam_obj);bpy.context.scene.camera=cam_obj
cam_obj.location=(W/2-0.5,-L/2+0.5,H*0.7)
cam_obj.rotation_euler=(math.radians(60),0,math.radians(45))

sun=bpy.data.lights.new("Sun","SUN");sun.energy=3;sun.color=(1.0,0.95,0.9)
sun_obj=bpy.data.objects.new("Sun",sun)
bpy.context.collection.objects.link(sun_obj)
sun_obj.rotation_euler=(math.radians(50),math.radians(20),math.radians(-30))

amb=bpy.data.lights.new("Ambient","AREA");amb.energy=100;amb.size=8
amb_obj=bpy.data.objects.new("AmbientLight",amb)
bpy.context.collection.objects.link(amb_obj)
amb_obj.location=(0,0,H-0.5)

world=bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world=world;world.use_nodes=True
bg=world.node_tree.nodes.get("Background")
if bg:bg.inputs["Color"].default_value=(0.02,0.02,0.05,1.0);bg.inputs["Strength"].default_value=0.15
"""

    return script


# ═══════════════════════════════════════════════════════════════
# BLENDER EXECUTION
# ═══════════════════════════════════════════════════════════════

def run_blender(script: str, output_file: str, timeout: int = 0) -> subprocess.CompletedProcess:
    """
    Запуск Blender CLI с валидацией скрипта и проверкой результата.
    """
    if timeout <= 0:
        timeout = settings.BLENDER_TIMEOUT

    job_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}.py")

    # Валидация синтаксиса
    try:
        compile(script, f"<{job_id}>", "exec")
    except SyntaxError as e:
        raise ValueError(f"Script syntax error: {e}")

    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)

    with open(script_path, "w") as f:
        f.write(script)

    try:
        result = subprocess.run(
            [settings.BLENDER_PATH, "--background", "--factory-startup",
             "--log-level", "0", "--python", script_path],
            capture_output=True, text=True, timeout=timeout,
        )

        # Проверка returncode
        if result.returncode != 0:
            stderr_tail = (result.stderr or "")[-500:]
            raise RuntimeError(
                f"Blender exited with code {result.returncode}: {stderr_tail}"
            )

        return result

    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Blender timeout ({timeout}s)")
    except (RuntimeError, TimeoutError):
        raise
    except Exception as e:
        raise RuntimeError(f"Blender failed: {e}")
    finally:
        if os.path.exists(script_path):
            try:
                os.remove(script_path)
            except OSError:
                pass
