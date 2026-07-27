"""
Blender Microservice — генерация зданий (GLB) и интерьеров (PNG)
Эндпоинты:
  POST /api/v1/generate           → GLB или PNG (единый endpoint с роутингом)
  POST /api/v1/generate/building  → GLB файл (legacy)
  POST /api/v1/render/interior    → PNG файл (legacy)
  GET  /health
"""
import os
import sys
import uuid
import subprocess
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# Добавить путь к промт-парсеру
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from promt_parser import fallback_regex_parse, get_generation_type, DEFAULT_FURNITURE

app = Flask(__name__)
CORS(app)

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")
BLENDER = os.environ.get("BLENDER_PATH", "blender")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# BUILDING GENERATOR
# ═══════════════════════════════════════════════════════════════
def parse_building_params(text):
    t = text.lower()
    p = {}
    wn = {'одно':1,'двух':2,'трёх':3,'трех':3,'четыр':4,'пяти':5,'шести':6}
    for w, n in wn.items():
        if w in t and ('этаж' in t or 'уровн' in t):
            p['floors'] = n
    import re
    fm = re.search(r'(\d+)\s*(?:этаж|floor)', t)
    if fm: p['floors'] = int(fm.group(1))
    dm = re.search(r'(\d+)\s*[×xх]\s*(\d+)', t)
    if dm: p['width'] = int(dm.group(1)); p['length'] = int(dm.group(2))
    if 'плоск' in t: p['roof_type'] = 'flat'
    elif 'вальм' in t: p['roof_type'] = 'hip'
    elif 'двускат' in t or 'скатн' in t: p['roof_type'] = 'gabled'
    mat_map = {'кирпич':'brick','дерев':'wood','стекл':'glass','камен':'stone','бетон':'concrete','штукат':'plaster'}
    for word, mat in mat_map.items():
        if word in t: p['facade_material'] = mat
    p['has_balcony'] = 'балкон' in t
    p['has_terrace'] = 'террас' in t
    p['has_garage'] = 'гараж' in t
    if 'офис' in t: p['type'] = 'office'
    elif 'коттедж' in t: p['type'] = 'cottage'
    elif 'вилл' in t: p['type'] = 'villa'
    else: p['type'] = 'house'
    return p


def safe_val(value, default, valid_values=None):
    """Валидация параметра перед подстановкой в bpy-скрипт.
    Возвращает default если value невалидно."""
    if value is None:
        return default
    if valid_values is not None and value not in valid_values:
        return default
    return value


def generate_bpy_script(params):
    # Валидация всех параметров (Step 1.3)
    W = safe_val(params.get('width'), 10, range(1, 201))
    L = safe_val(params.get('length'), 12, range(1, 201))
    floors = safe_val(params.get('floors'), 2, range(1, 21))
    fH = safe_val(params.get('floor_height'), 3.0)
    thick = safe_val(params.get('wall_thickness'), 0.3)
    roof_type = safe_val(params.get('roof_type'), 'gabled', ['gabled', 'flat', 'hip'])
    mat = safe_val(params.get('facade_material'), 'plaster',
                   ['brick', 'wood', 'glass', 'stone', 'concrete', 'plaster'])
    has_balcony = bool(params.get('has_balcony', False))
    has_terrace = bool(params.get('has_terrace', False))
    has_garage = bool(params.get('has_garage', False))

    colors = {'brick':(0.71,0.40,0.12),'wood':(0.55,0.41,0.13),'glass':(0.53,0.81,0.92),
              'plaster':(0.91,0.88,0.83),'stone':(0.50,0.50,0.50),'concrete':(0.63,0.63,0.63)}
    wr, wg, wb = colors.get(mat, (0.91, 0.88, 0.83))
    total_h = floors * fH

    script = f'''import bpy, os, math
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
W={W};L={L};floors={floors};fH={fH};thick={thick};total_h=floors*fH
def make_mat(n,c,r=0.8,m=0.0):
    mat=bpy.data.materials.new(n);mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:bsdf.inputs["Base Color"].default_value=(*c,1.0);bsdf.inputs["Roughness"].default_value=r;bsdf.inputs["Metallic"].default_value=m
    return mat
wall_mat=make_mat("Wall",({wr},{wg},{wb}));roof_mat=make_mat("Roof",(0.545,0.271,0.075))
glass_mat=make_mat("Glass",(0.8,0.9,1.0),0.05,0.1);ground_mat=make_mat("Grass",(0.29,0.49,0.25))
concrete_mat=make_mat("Concrete",(0.5,0.5,0.5),0.95);door_mat=make_mat("Door",(0.29,0.22,0.16))
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,-0.15))
fnd=bpy.context.active_object;fnd.name="Foundation";fnd.scale=(W/2+0.3,L/2+0.3,0.15)
bpy.ops.object.transform_apply(scale=True);fnd.data.materials.append(concrete_mat)
for floor in range(floors):
    z=floor*fH+fH/2
    for side,(sx,sy) in [("F",(0,-L/2)),("B",(0,L/2)),("L",(-W/2,0)),("R",(W/2,0))]:
        is_x=side in ("L","R")
        bpy.ops.mesh.primitive_cube_add(size=1,location=(sx,sy,z))
        w=bpy.context.active_object;w.name=f"Wall_{{side}}_{{floor}}"
        w.scale=((thick if is_x else W)/2,(L if is_x else thick)/2,fH/2)
        bpy.ops.object.transform_apply(scale=True);w.data.materials.append(wall_mat)
    n_win=max(2,W//3)
    for i in range(n_win):
        x=-W/2+(i+1)*W/(n_win+1)
        bpy.ops.mesh.primitive_plane_add(size=1,location=(x,-L/2-thick/2-0.01,floor*fH+fH*0.4))
        g=bpy.context.active_object;g.name=f"Window_{{floor}}_{{i}}";g.scale=(1.2,0.02,1.5);g.data.materials.append(glass_mat)
    if floor>0:
        bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,floor*fH))
        slab=bpy.context.active_object;slab.name=f"Slab_{{floor}}";slab.scale=(W/2,L/2,0.1)
        bpy.ops.object.transform_apply(scale=True);slab.data.materials.append(concrete_mat)
rh=2.5
if "{roof_type}"=="gabled":
    verts=[(-W/2-0.3,-L/2-0.3,total_h),(W/2+0.3,-L/2-0.3,total_h),(W/2+0.3,L/2+0.3,total_h),(-W/2-0.3,L/2+0.3,total_h),(0,-L/2-0.3,total_h+rh),(0,L/2+0.3,total_h+rh)]
    faces=[(0,1,4),(2,3,5),(0,3,5,4),(1,2,5,4)]
    mesh=bpy.data.meshes.new("RoofMesh");mesh.from_pydata(verts,[],faces);mesh.update()
    roof=bpy.data.objects.new("Roof",mesh);bpy.context.collection.objects.link(roof);roof.data.materials.append(roof_mat)
elif "{roof_type}"=="flat":
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,total_h+0.1))
    roof=bpy.context.active_object;roof.name="Roof";roof.scale=(W/2+0.3,L/2+0.3,0.1)
    bpy.ops.object.transform_apply(scale=True);roof.data.materials.append(roof_mat)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2-thick/2-0.01,1.1))
door=bpy.context.active_object;door.name="Door";door.scale=(0.5,0.04,1.1);door.data.materials.append(door_mat)
bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.data.objects:
    if obj.name not in ('Ground','Camera','Sun') and obj.type=='MESH':
        obj.select_set(True)
bpy.context.view_layer.objects.active=bpy.data.objects.get('Foundation')
bpy.ops.object.join()
bpy.context.active_object.name='Building'
'''
    if has_balcony:
        script += '''
for floor in range(1,floors):
    z=floor*fH
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2-1.5,z+0.05))
    balc=bpy.context.active_object;balc.name=f"Balcony_{floor}";balc.scale=(1.5,0.75,0.05)
    bpy.ops.object.transform_apply(scale=True);balc.data.materials.append(concrete_mat)
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2-2.2,z+0.6))
    rail=bpy.context.active_object;rail.name=f"Railing_{floor}";rail.scale=(1.5,0.03,0.5);rail.data.materials.append(wall_mat)
'''
    script += f'''
bpy.ops.mesh.primitive_plane_add(size=50,location=(0,0,-0.01))
gnd=bpy.context.active_object;gnd.name="Ground";gnd.data.materials.append(ground_mat)
cam=bpy.data.cameras.new("Camera");cam_obj=bpy.data.objects.new("Camera",cam)
bpy.context.scene.collection.objects.link(cam_obj);bpy.context.scene.camera=cam_obj
cam_obj.location=(W*1.5,-L*1.5,total_h*1.2);cam_obj.rotation_euler=(math.radians(60),0,math.radians(45))
sun=bpy.data.lights.new("Sun","SUN");sun.energy=3
sun_obj=bpy.data.objects.new("Sun",sun);bpy.context.collection.objects.link(sun_obj)
sun_obj.rotation_euler=(math.radians(45),math.radians(15),math.radians(30))
world=bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world=world;world.use_nodes=True
bg=world.node_tree.nodes.get("Background")
if bg:bg.inputs["Color"].default_value=(0.5,0.7,1.0,1.0);bg.inputs["Strength"].default_value=1.0
'''
    return script


# ═══════════════════════════════════════════════════════════════
# INTERIOR RENDERER
# ═══════════════════════════════════════════════════════════════
def generate_interior_script(params):
    w = params.get('width', 6)
    l = params.get('length', 8)
    h = params.get('height', 3)
    style = params.get('style', 'modern')
    furniture = params.get('furniture', ['sofa', 'table', 'chandelier'])

    style_colors = {
        'modern':       {'wall':(0.96,0.96,0.96),'floor':(0.77,0.66,0.51),'accent':(0.17,0.24,0.31)},
        'classic':      {'wall':(0.94,0.90,0.83),'floor':(0.55,0.41,0.08),'accent':(0.55,0.0,0.0)},
        'scandinavian': {'wall':(0.98,0.98,0.98),'floor':(0.83,0.72,0.59),'accent':(0.56,0.74,0.56)},
        'loft':         {'wall':(0.63,0.63,0.63),'floor':(0.42,0.42,0.42),'accent':(1.0,0.42,0.21)},
        'minimalist':   {'wall':(1.0,1.0,1.0),'floor':(0.88,0.85,0.80),'accent':(0.0,0.0,0.0)},
        'hitech':       {'wall':(0.9,0.9,0.95),'floor':(0.3,0.3,0.35),'accent':(0.0,0.6,0.8)},
    }
    sc = style_colors.get(style, style_colors['modern'])

    script = f'''import bpy, math
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
W={w};L={l};H={h}
def make_mat(n,c,r=0.8,e=0.0):
    mat=bpy.data.materials.new(n);mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value=(*c,1.0);bsdf.inputs["Roughness"].default_value=r
        if e>0:
            try:bsdf.inputs["Emission Color"].default_value=(*c,1.0)
            except:bsdf.inputs["Emission"].default_value=(*c,1.0)
            try:bsdf.inputs["Emission Strength"].default_value=e
            except:pass
    return mat
wall_mat=make_mat("Wall",{sc['wall']},0.9)
floor_mat=make_mat("Floor",{sc['floor']},0.6)
ceiling_mat=make_mat("Ceiling",(1,1,1),0.95)
accent_mat=make_mat("Accent",{sc['accent']},0.7)
bpy.ops.mesh.primitive_plane_add(size=1,location=(0,0,0))
fl=bpy.context.active_object;fl.name="Floor";fl.scale=(W/2,L/2,1)
bpy.ops.object.transform_apply(scale=True);fl.data.materials.append(floor_mat)
bpy.ops.mesh.primitive_plane_add(size=1,location=(0,0,H))
ceil=bpy.context.active_object;ceil.name="Ceiling";ceil.scale=(W/2,L/2,1)
ceil.rotation_euler.x=math.pi
bpy.ops.object.transform_apply(scale=True,rotation=True);ceil.data.materials.append(ceiling_mat)
for name,(sx,sy),(dx,dy) in [("Front",(0,-L/2),(W,0.15)),("Back",(0,L/2),(W,0.15)),("Left",(-W/2,0),(0.15,L)),("Right",(W/2,0),(0.15,L))]:
    bpy.ops.mesh.primitive_cube_add(size=1,location=(sx,sy,H/2))
    wall=bpy.context.active_object;wall.name=name;wall.scale=(dx/2,dy/2,H/2)
    bpy.ops.object.transform_apply(scale=True);wall.data.materials.append(wall_mat)
'''
    if 'sofa' in furniture:
        script += '''
sofa_mat=make_mat("Sofa",(0.29,0.29,0.29),0.85)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2+1,0.3))
seat=bpy.context.active_object;seat.name="Sofa_Seat";seat.scale=(1,0.5,0.3)
bpy.ops.object.transform_apply(scale=True);seat.data.materials.append(sofa_mat)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2+1.35,0.65))
back=bpy.context.active_object;back.name="Sofa_Back";back.scale=(1,0.1,0.35)
bpy.ops.object.transform_apply(scale=True);back.data.materials.append(sofa_mat)
'''
    if 'table' in furniture:
        script += '''
table_mat=make_mat("Table",(0.55,0.41,0.08),0.6)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,0.75))
top=bpy.context.active_object;top.name="Table_Top";top.scale=(0.6,0.4,0.04)
bpy.ops.object.transform_apply(scale=True);top.data.materials.append(table_mat)
for dx,dy in [(-1,-1),(1,-1),(-1,1),(1,1)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.03,depth=0.75,location=(dx*0.5,dy*0.3,0.375))
    leg=bpy.context.active_object;leg.name="Table_Leg";leg.data.materials.append(table_mat)
'''
    if 'bed' in furniture:
        script += '''
bed_mat=make_mat("Bed",(0.94,0.94,0.94),0.9)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,0.25))
mattress=bpy.context.active_object;mattress.name="Mattress";mattress.scale=(0.9,1,0.25)
bpy.ops.object.transform_apply(scale=True);mattress.data.materials.append(bed_mat)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0.95,0.6))
hb=bpy.context.active_object;hb.name="Headboard";hb.scale=(0.9,0.05,0.6)
hb.data.materials.append(make_mat("Headboard",(0.24,0.17,0.12),0.7))
'''
    if 'chandelier' in furniture:
        script += '''
bpy.ops.mesh.primitive_cylinder_add(radius=0.01,depth=1,location=(0,0,H-0.5))
wire=bpy.context.active_object;wire.name="Wire"
wire.data.materials.append(make_mat("Metal",(0.2,0.2,0.2),0.3,0.8))
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2,location=(0,0,H-1))
shade=bpy.context.active_object;shade.name="Shade"
shade.data.materials.append(make_mat("Light",(1,0.96,0.88),0.5,5.0))
light_data=bpy.data.lights.new("Chandelier","POINT");light_data.energy=500;light_data.color=(1.0,0.95,0.85)
light_obj=bpy.data.objects.new("Chandelier",light_data)
bpy.context.collection.objects.link(light_obj);light_obj.location=(0,0,H-1)
'''
    if 'desk' in furniture:
        script += '''
desk_mat=make_mat("Desk",(0.6,0.45,0.25),0.65)
bpy.ops.mesh.primitive_cube_add(size=1,location=(L/2-1,0,0.75))
dtop=bpy.context.active_object;dtop.name="Desk_Top";dtop.scale=(0.5,0.8,0.03)
bpy.ops.object.transform_apply(scale=True);dtop.data.materials.append(desk_mat)
for dx,dy in [(-1,-1),(1,-1),(-1,1),(1,1)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.025,depth=0.75,location=(L/2-1+dx*0.45,dy*0.7,0.375))
    dleg=bpy.context.active_object;dleg.name="Desk_Leg";dleg.data.materials.append(desk_mat)
'''
    if 'wardrobe' in furniture:
        script += '''
ward_mat=make_mat("Wardrobe",(0.45,0.32,0.18),0.7)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,L/2-0.5,0.9))
ward=bpy.context.active_object;ward.name="Wardrobe";ward.scale=(0.8,0.4,0.9)
bpy.ops.object.transform_apply(scale=True);ward.data.materials.append(ward_mat)
'''
    if 'nightstand' in furniture:
        script += '''
ns_mat=make_mat("Nightstand",(0.5,0.38,0.22),0.7)
bpy.ops.mesh.primitive_cube_add(size=1,location=(-1.2,0.5,0.25))
ns=bpy.context.active_object;ns.name="Nightstand";ns.scale=(0.25,0.25,0.25)
bpy.ops.object.transform_apply(scale=True);ns.data.materials.append(ns_mat)
'''
    if 'bookshelf' in furniture:
        script += '''
shelf_mat=make_mat("Bookshelf",(0.5,0.35,0.2),0.7)
for i in range(3):
    bpy.ops.mesh.primitive_cube_add(size=1,location=(-W/2+0.2,L/2-0.3,0.4+i*0.5))
    sh=bpy.context.active_object;sh.name=f"Shelf_{i}";sh.scale=(0.15,0.25,0.02)
    bpy.ops.object.transform_apply(scale=True);sh.data.materials.append(shelf_mat)
'''
    if 'sink' in furniture:
        script += '''
sink_mat=make_mat("Sink",(0.9,0.9,0.9),0.3,0.1)
bpy.ops.mesh.primitive_cylinder_add(radius=0.2,depth=0.15,location=(-W/2+0.5,0,0.9))
sn=bpy.context.active_object;sn.name="Sink";sn.data.materials.append(sink_mat)
'''
    if 'stove' in furniture:
        script += '''
stove_mat=make_mat("Stove",(0.2,0.2,0.2),0.5,0.3)
bpy.ops.mesh.primitive_cube_add(size=1,location=(-W/2+0.5,L/2-0.5,0.45))
stv=bpy.context.active_object;stv.name="Stove";stv.scale=(0.3,0.3,0.45)
bpy.ops.object.transform_apply(scale=True);stv.data.materials.append(stove_mat)
'''
    if 'bathtub' in furniture:
        script += '''
tub_mat=make_mat("Bathtub",(0.95,0.95,0.95),0.2)
bpy.ops.mesh.primitive_cylinder_add(radius=0.5,depth=0.4,location=(L/2-1,0,0.2))
tub=bpy.context.active_object;tub.name="Bathtub";tub.data.materials.append(tub_mat)
'''
    if 'chair' in furniture:
        script += '''
chair_mat=make_mat("Chair",(0.3,0.3,0.3),0.8)
bpy.ops.mesh.primitive_cube_add(size=1,location=(L/2-1,0.8,0.45))
chseat=bpy.context.active_object;chseat.name="Chair_Seat";chseat.scale=(0.2,0.2,0.03)
bpy.ops.object.transform_apply(scale=True);chseat.data.materials.append(chair_mat)
bpy.ops.mesh.primitive_cube_add(size=1,location=(L/2-1,0.8,0.7))
chback=bpy.context.active_object;chback.name="Chair_Back";chback.scale=(0.2,0.03,0.25)
bpy.ops.object.transform_apply(scale=True);chback.data.materials.append(chair_mat)
'''
    script += '''
cam=bpy.data.cameras.new("InteriorCam");cam.lens=24
cam_obj=bpy.data.objects.new("Camera",cam)
bpy.context.scene.collection.objects.link(cam_obj);bpy.context.scene.camera=cam_obj
cam_obj.location=(W/2-0.5,-L/2+0.5,H*0.7)
cam_obj.rotation_euler=(math.radians(60),0,math.radians(45))
sun=bpy.data.lights.new("Sun","SUN");sun.energy=3
sun_obj=bpy.data.objects.new("Sun",sun)
bpy.context.collection.objects.link(sun_obj)
sun_obj.rotation_euler=(math.radians(50),math.radians(20),math.radians(-30))
world=bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world=world;world.use_nodes=True
bg=world.node_tree.nodes.get("Background")
if bg:bg.inputs["Color"].default_value=(0.02,0.02,0.05,1.0);bg.inputs["Strength"].default_value=0.1
'''
    return script


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════
@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "blender-service", "blender": BLENDER})


# ═══════════════════════════════════════════════════════════════
# UNIFIED GENERATE ENDPOINT (Step 1.2)
# ═══════════════════════════════════════════════════════════════
@app.route("/api/v1/generate", methods=["POST"])
def generate():
    """Единый endpoint: промт → парсинг → роутинг → генерация."""
    data = request.json or {}
    prompt = data.get("prompt", "")
    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    # Парсинг промта
    params = fallback_regex_parse(prompt)

    # Роутинг по типу объекта
    gen_type = get_generation_type(params)

    if gen_type == "interior":
        # Интерьер/комната → PNG
        room_type = params.get("room_type", "living")
        furniture = params.get("furniture") or DEFAULT_FURNITURE.get(room_type, ["sofa", "table", "chandelier"])
        interior_params = {
            "width": params.get("width_m", 6),
            "length": params.get("length_m", 8),
            "height": params.get("height_m", 3),
            "style": params.get("style", "modern"),
            "furniture": furniture,
        }
        script = generate_interior_script(interior_params)
        return _execute_blender_render(script, "png", f"archai_interior")
    else:
        # Здание → GLB
        building_params = {
            "width": params.get("width_m", 10),
            "length": params.get("length_m", 12),
            "floors": params.get("floors", 2),
            "roof_type": params.get("roof_type", "gabled"),
            "facade_material": params.get("material", "plaster"),
            "has_balcony": "balcony" in params.get("features", []),
            "has_terrace": "terrace" in params.get("features", []),
            "has_garage": "garage" in params.get("features", []),
        }
        script = generate_bpy_script(building_params)
        return _execute_blender_export(script, "glb", "archai_building")


def _execute_blender_export(script, ext, prefix):
    """Валидация + запуск Blender CLI для экспорта."""
    job_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(OUTPUT_DIR, f"{job_id}.py")
    output_file = os.path.join(OUTPUT_DIR, f"{job_id}.{ext}")

    # Валидация синтаксиса
    try:
        compile(script, f"<{job_id}>", "exec")
    except SyntaxError as e:
        return jsonify({"error": f"Script syntax error: {e}"}), 500

    export_cmd = f"\nimport bpy\nbpy.ops.export_scene.gltf(filepath=r'{output_file}', export_format='GLB')\n"
    with open(script_path, "w") as f:
        f.write(script + export_cmd)

    try:
        result = subprocess.run(
            [BLENDER, "--background", "--factory-startup", "--log-level", "0", "--python", script_path],
            capture_output=True, text=True, timeout=120
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Blender timeout (120s)"}), 504
    except Exception as e:
        return jsonify({"error": f"Blender failed: {e}"}), 500
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)

    if os.path.exists(output_file):
        return send_file(output_file, as_attachment=True,
                        download_name=f"{prefix}_{job_id}.{ext}",
                        mimetype="model/gltf-binary")
    return jsonify({"error": "Blender export failed", "stderr": (result.stderr or "")[-500:]}), 500


def _execute_blender_render(script, ext, prefix):
    """Валидация + запуск Blender CLI для рендера."""
    job_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(OUTPUT_DIR, f"{job_id}_int.py")
    output_file = os.path.join(OUTPUT_DIR, f"{job_id}_int.{ext}")

    # Валидация синтаксиса
    try:
        compile(script, f"<{job_id}>", "exec")
    except SyntaxError as e:
        return jsonify({"error": f"Script syntax error: {e}"}), 500

    render_cmd = (
        "\nimport bpy"
        f"\nbpy.context.scene.render.filepath = r'{output_file}'"
        "\nbpy.context.scene.render.engine = 'BLENDER_EEVEE'"
        "\nbpy.context.scene.render.resolution_x = 640"
        "\nbpy.context.scene.render.resolution_y = 480"
        "\nbpy.ops.render.render(write_still=True)"
        "\n"
    )
    with open(script_path, "w") as f:
        f.write(script + render_cmd)

    try:
        result = subprocess.run(
            [BLENDER, "--background", "--factory-startup", "--log-level", "0", "--python", script_path],
            capture_output=True, text=True, timeout=300
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Blender render timeout (300s)"}), 504
    except Exception as e:
        return jsonify({"error": f"Blender failed: {e}"}), 500
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)

    if os.path.exists(output_file):
        return send_file(output_file, as_attachment=True,
                        download_name=f"{prefix}_{job_id}.{ext}",
                        mimetype="image/png")
    return jsonify({"error": "Render failed", "stderr": (result.stderr or "")[-500:]}), 500


# ═══════════════════════════════════════════════════════════════
# LEGACY ENDPOINTS (обратная совместимость — делегируют в unified)
# ═══════════════════════════════════════════════════════════════
@app.route("/api/v1/generate/building", methods=["POST"])
def generate_building_legacy():
    """Legacy endpoint — delegates to unified /api/v1/generate."""
    data = request.json or {}
    data["object_type"] = "building"
    # Обернуть prompt в data если передан только prompt
    if "prompt" not in data:
        # Старый формат: параметры напрямую
        prompt_parts = []
        if data.get("width") and data.get("length"):
            prompt_parts.append(f"{data['width']}×{data['length']}")
        if data.get("floors"):
            prompt_parts.append(f"{data['floors']} этажа")
        data["prompt"] = " ".join(prompt_parts) or "дом"
    return generate()


@app.route("/api/v1/render/interior", methods=["POST"])
def render_interior_legacy():
    """Legacy endpoint — delegates to unified /api/v1/generate."""
    data = request.json or {}
    data["object_type"] = "interior"
    if "prompt" not in data:
        style = data.get("style", "modern")
        data["prompt"] = f"интерьер в стиле {style}"
    return generate()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8082))
    print(f"🏗️ Blender Service starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
