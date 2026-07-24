"""
ArchAI — Full Server
Serves frontend + proxies Claude API + generates Blender scripts.

Endpoints:
    GET  /                           — Web interface
    GET  /api/v1/health              — Health check
    POST /api/v1/proxy/claude        — Claude API proxy
    POST /api/v1/generate/building   — Text → 3D params + bpy script
    POST /api/v1/render/interior     — Interior params → bpy render script
"""

import os
import sys
import json
import re
import uuid
import httpx
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
PORT = int(os.environ.get("PORT", 8080))
FRONTEND_DIR = os.path.join(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
BLENDER_DIR = os.path.join(os.path.dirname(__file__), "blender")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════
app = Flask(__name__)
CORS(app)

# ═══════════════════════════════════════════════════════════════
# BUILDING PARAMETER PARSER (Russian text → structured params)
# ═══════════════════════════════════════════════════════════════
def parse_building_params(text):
    t = text.lower()
    p = {}

    # Floors
    wn = {'одно':1,'двух':2,'двуэт':2,'трёх':3,'трех':3,'четыр':4,'пяти':5,'шести':6}
    for w, n in wn.items():
        if w in t and ('этаж' in t or 'уровн' in t):
            p['floors'] = n
    fm = re.search(r'(\d+)\s*(?:этаж|floor)', t)
    if fm:
        p['floors'] = int(fm.group(1))

    # Dimensions
    dm = re.search(r'(\d+)\s*[×xх]\s*(\d+)', t)
    if dm:
        p['width'] = int(dm.group(1))
        p['length'] = int(dm.group(2))

    # Roof
    if 'плоск' in t:
        p['roof_type'] = 'flat'
    elif 'вальм' in t:
        p['roof_type'] = 'hip'
    elif 'двускатн' in t or 'скатн' in t:
        p['roof_type'] = 'gabled'

    # Material
    mat_map = {'кирпич':'brick','дерев':'wood','стекл':'glass','камен':'stone','бетон':'concrete','штукатурк':'plaster'}
    for word, mat in mat_map.items():
        if word in t:
            p['facade_material'] = mat

    # Options
    p['has_balcony'] = 'балкон' in t
    p['has_terrace'] = 'террас' in t
    p['has_garage'] = 'гараж' in t

    # Type
    if 'офис' in t or 'office' in t:
        p['type'] = 'office'
    elif 'коттедж' in t or 'cottage' in t:
        p['type'] = 'cottage'
    elif 'вилл' in t or 'villa' in t:
        p['type'] = 'villa'
    else:
        p['type'] = 'house'

    return p

# ═══════════════════════════════════════════════════════════════
# BPY SCRIPT GENERATOR (template-based, works without GPU)
# ═══════════════════════════════════════════════════════════════
def generate_bpy_script(params):
    W = params.get('width', 10)
    L = params.get('length', 12)
    floors = params.get('floors', 2)
    fH = params.get('floor_height', 3.0)
    thick = params.get('wall_thickness', 0.3)
    roof_type = params.get('roof_type', 'gabled')
    mat = params.get('facade_material', 'plaster')
    has_balcony = params.get('has_balcony', False)
    has_terrace = params.get('has_terrace', False)
    has_garage = params.get('has_garage', False)

    # Material colors
    colors = {
        'brick': (0.71, 0.40, 0.12),
        'wood': (0.55, 0.41, 0.13),
        'glass': (0.53, 0.81, 0.92),
        'plaster': (0.91, 0.88, 0.83),
        'stone': (0.50, 0.50, 0.50),
        'concrete': (0.63, 0.63, 0.63),
    }
    wr, wg, wb = colors.get(mat, (0.91, 0.88, 0.83))
    total_h = floors * fH

    script = f'''import bpy
import os
import math

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

W = {W}
L = {L}
floors = {floors}
fH = {fH}
thick = {thick}
total_h = floors * fH

def make_mat(name, color, rough=0.8, metal=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
    return mat

wall_mat = make_mat("Wall", ({wr}, {wg}, {wb}))
roof_mat = make_mat("Roof", (0.545, 0.271, 0.075))
glass_mat = make_mat("Glass", (0.8, 0.9, 1.0), 0.05, 0.1)
ground_mat = make_mat("Grass", (0.29, 0.49, 0.25))
concrete_mat = make_mat("Concrete", (0.5, 0.5, 0.5), 0.95)
door_mat = make_mat("Door", (0.29, 0.22, 0.16))

# Foundation
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.15))
fnd = bpy.context.active_object
fnd.name = "Foundation"
fnd.scale = (W/2+0.3, L/2+0.3, 0.15)
bpy.ops.object.transform_apply(scale=True)
fnd.data.materials.append(concrete_mat)

# Walls
for floor in range(floors):
    z = floor * fH + fH/2
    for side, (sx, sy) in [("F", (0, -L/2)), ("B", (0, L/2)), ("L", (-W/2, 0)), ("R", (W/2, 0))]:
        is_x = side in ("L", "R")
        bpy.ops.mesh.primitive_cube_add(size=1, location=(sx, sy, z))
        w = bpy.context.active_object
        w.name = f"Wall_{{side}}_{{floor}}"
        w.scale = ((thick if is_x else W)/2, (L if is_x else thick)/2, fH/2)
        bpy.ops.object.transform_apply(scale=True)
        w.data.materials.append(wall_mat)

    # Windows (front wall)
    n_win = max(2, W // 3)
    for i in range(n_win):
        x = -W/2 + (i+1)*W/(n_win+1)
        bpy.ops.mesh.primitive_plane_add(size=1, location=(x, -L/2-thick/2-0.01, floor*fH+fH*0.4))
        g = bpy.context.active_object
        g.name = f"Window_{{floor}}_{{i}}"
        g.scale = (1.2, 0.02, 1.5)
        g.data.materials.append(glass_mat)

    # Floor slab
    if floor > 0:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, floor*fH))
        slab = bpy.context.active_object
        slab.name = f"Slab_{{floor}}"
        slab.scale = (W/2, L/2, 0.1)
        bpy.ops.object.transform_apply(scale=True)
        slab.data.materials.append(concrete_mat)

# Roof
rh = 2.5
if "{roof_type}" == "gabled":
    verts = [
        (-W/2-0.3, -L/2-0.3, total_h), (W/2+0.3, -L/2-0.3, total_h),
        (W/2+0.3, L/2+0.3, total_h), (-W/2-0.3, L/2+0.3, total_h),
        (0, -L/2-0.3, total_h+rh), (0, L/2+0.3, total_h+rh),
    ]
    faces = [(0,1,4), (2,3,5), (0,3,5,4), (1,2,5,4)]
    mesh = bpy.data.meshes.new("RoofMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    roof = bpy.data.objects.new("Roof", mesh)
    bpy.context.collection.objects.link(roof)
    roof.data.materials.append(roof_mat)
elif "{roof_type}" == "flat":
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, total_h+0.1))
    roof = bpy.context.active_object
    roof.name = "Roof"
    roof.scale = (W/2+0.3, L/2+0.3, 0.1)
    bpy.ops.object.transform_apply(scale=True)
    roof.data.materials.append(roof_mat)

# Door
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -L/2-thick/2-0.01, 1.1))
door = bpy.context.active_object
door.name = "Door"
door.scale = (0.5, 0.04, 1.1)
door.data.materials.append(door_mat)
'''

    # Balcony
    if has_balcony:
        script += '''
# Balcony
for floor in range(1, floors):
    z = floor * fH
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -L/2-1.5, z+0.05))
    balc = bpy.context.active_object
    balc.name = f"Balcony_{floor}"
    balc.scale = (1.5, 0.75, 0.05)
    bpy.ops.object.transform_apply(scale=True)
    balc.data.materials.append(concrete_mat)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -L/2-2.2, z+0.6))
    rail = bpy.context.active_object
    rail.name = f"Railing_{floor}"
    rail.scale = (1.5, 0.03, 0.5)
    rail.data.materials.append(wall_mat)
'''

    # Terrace
    if has_terrace:
        script += '''
# Terrace
bpy.ops.mesh.primitive_cube_add(size=1, location=(W/2+2, 0, 0.05))
terr = bpy.context.active_object
terr.name = "Terrace"
terr.scale = (1.5, L/2, 0.05)
bpy.ops.object.transform_apply(scale=True)
terr.data.materials.append(concrete_mat)
'''

    # Garage
    if has_garage:
        script += '''
# Garage
bpy.ops.mesh.primitive_cube_add(size=1, location=(-W/2-3, 0, 1.5))
garage = bpy.context.active_object
garage.name = "Garage"
garage.scale = (2, 2.5, 1.5)
bpy.ops.object.transform_apply(scale=True)
garage.data.materials.append(wall_mat)
bpy.ops.mesh.primitive_cube_add(size=1, location=(-W/2-3, -2.5, 1.2))
gd = bpy.context.active_object
gd.name = "GarageDoor"
gd.scale = (1.75, 0.04, 1.2)
gd.data.materials.append(door_mat)
'''

    # Ground + Camera + Light
    script += '''
# Ground
bpy.ops.mesh.primitive_plane_add(size=50, location=(0, 0, -0.01))
gnd = bpy.context.active_object
gnd.name = "Ground"
gnd.data.materials.append(ground_mat)

# Camera
cam = bpy.data.cameras.new("Camera")
cam_obj = bpy.data.objects.new("Camera", cam)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj
cam_obj.location = (W*1.5, -L*1.5, total_h*1.2)
cam_obj.rotation_euler = (math.radians(60), 0, math.radians(45))

# Sun
sun = bpy.data.lights.new("Sun", "SUN")
sun.energy = 3
sun_obj = bpy.data.objects.new("Sun", sun)
bpy.context.collection.objects.link(sun_obj)
sun_obj.rotation_euler = (math.radians(45), math.radians(15), math.radians(30))

# World
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value = (0.5, 0.7, 1.0, 1.0)
    bg.inputs["Strength"].default_value = 1.0
'''
    return script


# ═══════════════════════════════════════════════════════════════
# INTERIOR SCRIPT GENERATOR
# ═══════════════════════════════════════════════════════════════
def generate_interior_script(params):
    w = params.get('width', 6)
    l = params.get('length', 8)
    h = params.get('height', 3)
    style = params.get('style', 'modern')
    furniture = params.get('furniture', ['sofa', 'table', 'chandelier'])

    style_colors = {
        'modern':       {'wall': (0.96,0.96,0.96), 'floor': (0.77,0.66,0.51), 'accent': (0.17,0.24,0.31)},
        'classic':      {'wall': (0.94,0.90,0.83), 'floor': (0.55,0.41,0.08), 'accent': (0.55,0.0,0.0)},
        'scandinavian': {'wall': (0.98,0.98,0.98), 'floor': (0.83,0.72,0.59), 'accent': (0.56,0.74,0.56)},
        'loft':         {'wall': (0.63,0.63,0.63), 'floor': (0.42,0.42,0.42), 'accent': (1.0,0.42,0.21)},
        'minimalist':   {'wall': (1.0,1.0,1.0), 'floor': (0.88,0.85,0.80), 'accent': (0.0,0.0,0.0)},
    }
    sc = style_colors.get(style, style_colors['modern'])

    script = f'''import bpy
import math

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

W = {w}
L = {l}
H = {h}

def make_mat(name, color, rough=0.8, emit=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        if emit > 0:
            bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
            bsdf.inputs["Emission Strength"].default_value = emit
    return mat

wall_mat = make_mat("Wall", {sc['wall']}, 0.9)
floor_mat = make_mat("Floor", {sc['floor']}, 0.6)
ceiling_mat = make_mat("Ceiling", (1,1,1), 0.95)
accent_mat = make_mat("Accent", {sc['accent']}, 0.7)

# Floor
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
fl = bpy.context.active_object
fl.name = "Floor"
fl.scale = (W/2, L/2, 1)
bpy.ops.object.transform_apply(scale=True)
fl.data.materials.append(floor_mat)

# Ceiling
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, H))
ceil = bpy.context.active_object
ceil.name = "Ceiling"
ceil.scale = (W/2, L/2, 1)
ceil.rotation_euler.x = math.pi
bpy.ops.object.transform_apply(scale=True, rotation=True)
ceil.data.materials.append(ceiling_mat)

# Walls
for name, (sx, sy), (dx, dy) in [
    ("Front", (0, -L/2), (W, 0.15)),
    ("Back",  (0, L/2),  (W, 0.15)),
    ("Left",  (-W/2, 0), (0.15, L)),
    ("Right", (W/2, 0),  (0.15, L)),
]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(sx, sy, H/2))
    wall = bpy.context.active_object
    wall.name = name
    wall.scale = (dx/2, dy/2, H/2)
    bpy.ops.object.transform_apply(scale=True)
    wall.data.materials.append(wall_mat)
'''

    # Furniture
    if 'sofa' in furniture:
        script += '''
# Sofa
sofa_mat = make_mat("Sofa", (0.29, 0.29, 0.29), 0.85)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -L/2+1, 0.3))
seat = bpy.context.active_object
seat.name = "Sofa_Seat"
seat.scale = (1, 0.5, 0.3)
bpy.ops.object.transform_apply(scale=True)
seat.data.materials.append(sofa_mat)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -L/2+1.35, 0.65))
back = bpy.context.active_object
back.name = "Sofa_Back"
back.scale = (1, 0.1, 0.35)
bpy.ops.object.transform_apply(scale=True)
back.data.materials.append(sofa_mat)
'''

    if 'table' in furniture:
        script += '''
# Table
table_mat = make_mat("Table", (0.55, 0.41, 0.08), 0.6)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.75))
top = bpy.context.active_object
top.name = "Table_Top"
top.scale = (0.6, 0.4, 0.04)
bpy.ops.object.transform_apply(scale=True)
top.data.materials.append(table_mat)
for dx, dy in [(-1,-1),(1,-1),(-1,1),(1,1)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.75, location=(dx*0.5, dy*0.3, 0.375))
    leg = bpy.context.active_object
    leg.name = "Table_Leg"
    leg.data.materials.append(table_mat)
'''

    if 'bed' in furniture:
        script += '''
# Bed
bed_mat = make_mat("Bed", (0.94, 0.94, 0.94), 0.9)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.25))
mattress = bpy.context.active_object
mattress.name = "Mattress"
mattress.scale = (0.9, 1, 0.25)
bpy.ops.object.transform_apply(scale=True)
mattress.data.materials.append(bed_mat)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.95, 0.6))
hb = bpy.context.active_object
hb.name = "Headboard"
hb.scale = (0.9, 0.05, 0.6)
hb.data.materials.append(make_mat("Headboard", (0.24, 0.17, 0.12), 0.7))
'''

    if 'chandelier' in furniture:
        script += '''
# Chandelier
bpy.ops.mesh.primitive_cylinder_add(radius=0.01, depth=1, location=(0, 0, H-0.5))
wire = bpy.context.active_object
wire.name = "Wire"
wire.data.materials.append(make_mat("Metal", (0.2, 0.2, 0.2), 0.3, 0.8))
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2, location=(0, 0, H-1))
shade = bpy.context.active_object
shade.name = "Shade"
shade.data.materials.append(make_mat("Light", (1, 0.96, 0.88), 0.5, 5.0))
light_data = bpy.data.lights.new("Chandelier", "POINT")
light_data.energy = 500
light_data.color = (1.0, 0.95, 0.85)
light_obj = bpy.data.objects.new("Chandelier", light_data)
bpy.context.collection.objects.link(light_obj)
light_obj.location = (0, 0, H-1)
'''

    # Camera + world
    script += '''
# Camera
cam = bpy.data.cameras.new("InteriorCam")
cam.lens = 24
cam_obj = bpy.data.objects.new("Camera", cam)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj
cam_obj.location = (W/2-0.5, -L/2+0.5, H*0.7)
direction = (0, 0, H*0.4)
cam_obj.rotation_euler = (math.radians(60), 0, math.radians(45))

# Sun
sun = bpy.data.lights.new("Sun", "SUN")
sun.energy = 3
sun_obj = bpy.data.objects.new("Sun", sun)
bpy.context.collection.objects.link(sun_obj)
sun_obj.rotation_euler = (math.radians(50), math.radians(20), math.radians(-30))

# World
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value = (0.02, 0.02, 0.05, 1.0)
    bg.inputs["Strength"].default_value = 0.1
'''
    return script


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(FRONTEND_DIR, filename)

@app.route('/api/v1/health')
@app.route('/health')
def health():
    return jsonify({"status": "ok", "service": "archai-server"})

@app.route('/api/v1/proxy/claude', methods=['POST'])
def proxy_claude():
    """Proxy to Anthropic API."""
    if not ANTHROPIC_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY not set"}), 500

    data = request.json or {}
    headers = {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
    }
    try:
        r = httpx.post(
            f"{ANTHROPIC_BASE}/v1/messages",
            headers=headers,
            json=data,
            timeout=120.0,
        )
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502

@app.route('/api/v1/generate/building', methods=['POST'])
def generate_building():
    """Generate building bpy script from text prompt."""
    data = request.json or {}
    prompt = data.get('prompt', '')
    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    # Parse parameters
    params = parse_building_params(prompt)
    defaults = {
        "type": "house", "floors": 2, "width": 10, "length": 12,
        "roof_type": "gabled", "facade_material": "plaster",
    }
    for k, v in defaults.items():
        params.setdefault(k, v)

    # Try Claude for better parsing
    if ANTHROPIC_KEY:
        try:
            r = httpx.post(
                f"{ANTHROPIC_BASE}/v1/messages",
                headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 300,
                    "system": 'Извлеки параметры здания. ТОЛЬКО JSON: {"type":"house|office|cottage","floors":null,"width":null,"length":null,"roof_type":null,"facade_material":null,"has_balcony":false,"has_terrace":false,"has_garage":false} null=не упомянуто.',
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30.0,
            )
            if r.status_code == 200:
                raw = r.json()["content"][0]["text"]
                parsed = json.loads(raw.replace("```json", "").replace("```", "").strip())
                for k, v in parsed.items():
                    if v is not None and v != "null":
                        params[k] = v
        except Exception:
            pass

    # Generate script
    script = generate_bpy_script(params)

    job_id = uuid.uuid4().hex[:8]

    return jsonify({
        "job_id": job_id,
        "params": params,
        "script": script,
        "prompt": prompt,
    })

@app.route('/api/v1/render/interior', methods=['POST'])
def render_interior():
    """Generate interior bpy script."""
    data = request.json or {}
    script = generate_interior_script(data)
    job_id = uuid.uuid4().hex[:8]

    return jsonify({
        "job_id": job_id,
        "params": data,
        "script": script,
    })


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print(f"🏗️  ArchAI Server starting on port {PORT}")
    print(f"📡 Claude API: {'configured' if ANTHROPIC_KEY else 'not set'}")
    print(f"🌐 http://localhost:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
