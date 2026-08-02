#!/usr/bin/env python3
"""
AI_Arhitector — Enhanced Render Pipeline

Полный пайплайн: геометрия + PBR + HDRI + мебель + постобработка.
Использует generate_building.py + asset_loader.py + compositor.

Запуск на Kaggle:
  python3 enhanced_render.py --quality 4k --scene exterior --style modern
  python3 enhanced_render.py --quality 4k --scene interior --room living
"""

import subprocess, os, time, sys, argparse, urllib.request, tarfile

print("=" * 60)
print("AI_Arhitector — Enhanced Render Pipeline")
print("=" * 60)

# ============================================================
# ARGS
# ============================================================
parser = argparse.ArgumentParser()
parser.add_argument("--quality", default="4k", choices=["4k", "8k", "16k"])
parser.add_argument("--scene", default="exterior", choices=["exterior", "interior"])
parser.add_argument("--style", default="modern", help="Building style")
parser.add_argument("--room", default="living", help="Room type for interior")
parser.add_argument("--width", type=int, default=12, help="Building width (m)")
parser.add_argument("--length", type=int, default=10, help="Building length (m)")
parser.add_argument("--floors", type=int, default=2, help="Number of floors")
parser.add_argument("--assets", default="/kaggle/input/architect-assets", help="Assets directory")
args = parser.parse_args()

QUALITY = args.quality
SCENE = args.scene

CONFIGS = {
    "4k":  {"w": 3840,  "h": 2160,  "samples": 256,  "tiles_x": 1, "tiles_y": 1},
    "8k":  {"w": 7680,  "h": 4320,  "samples": 256,  "tiles_x": 2, "tiles_y": 2},
    "16k": {"w": 15360, "h": 8640,  "samples": 2048, "tiles_x": 4, "tiles_y": 3},
}
cfg = CONFIGS[QUALITY]

print(f"Scene: {SCENE} | Quality: {QUALITY} | Style: {args.style}")

# ============================================================
# STEP 1: Blender 4.0.2
# ============================================================
BLENDER_DIR = "/opt/blender4"
BLENDER = f"{BLENDER_DIR}/blender"

print(f"\n[1/7] Blender 4.0.2...")
t0 = time.time()
if not os.path.exists(BLENDER):
    url = "https://mirror.clarkson.edu/blender/release/Blender4.0/blender-4.0.2-linux-x64.tar.xz"
    urllib.request.urlretrieve(url, "/tmp/b4.tar.xz")
    with tarfile.open("/tmp/b4.tar.xz") as tf:
        tf.extractall("/opt/")
    os.rename("/opt/blender-4.0.2-linux-x64", BLENDER_DIR)
    os.remove("/tmp/b4.tar.xz")
print(f"  {time.time()-t0:.0f}s")

# GPU
r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                   capture_output=True, text=True, timeout=10)
print(f"  GPU: {r.stdout.strip()}")

# ============================================================
# STEP 2: Prepare bpy script
# ============================================================
print(f"\n[2/7] Preparing scene script...")

ASSETS_DIR = args.assets
MANIFEST_PATH = os.path.join(ASSETS_DIR, "manifest.json")

# Try loading v9.1.0 shared modules
try:
    sys.path.insert(0, "/kaggle/input/architect-shared")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
    from shared.pbr_scraper import PBRScraper
    pbr_scraper = PBRScraper(cache_dir=os.path.join(ASSETS_DIR, "textures"))
    HAS_PBR_SCRAPER = True
    print("  v9.1.0 PBRScraper loaded")
except ImportError:
    HAS_PBR_SCRAPER = False
    print("  PBRScraper not available, using local assets")

try:
    from shared.cad_builder import WallBuilder, WallSpec, WallOpening, BuildingSpec
    HAS_CAD = True
    print("  v9.1.0 CAD Builder loaded")
except ImportError:
    HAS_CAD = False
    print("  CAD Builder not available, using bpy geometry")

try:
    from shared.compliance import ComplianceChecker
    HAS_COMPLIANCE = True
    print("  v9.1.0 Compliance Checker loaded")
except ImportError:
    HAS_COMPLIANCE = False

# Check for assets
has_assets = os.path.exists(MANIFEST_PATH)
has_textures = os.path.exists(os.path.join(ASSETS_DIR, "textures"))
has_hdris = os.path.exists(os.path.join(ASSETS_DIR, "hdris"))
has_models = os.path.exists(os.path.join(ASSETS_DIR, "models"))

print(f"  Assets: {ASSETS_DIR}")
print(f"  Manifest: {'✅' if has_assets else '❌'}")
print(f"  Textures: {'✅' if has_textures else '❌'}")
print(f"  HDRIs: {'✅' if has_hdris else '❌'}")
print(f"  Models: {'✅' if has_models else '❌'}")

# Load asset_loader.py
ASSET_LOADER_PATH = "/tmp/asset_loader.py"
if os.path.exists("/kaggle/input/architect-scripts/asset_loader.py"):
    loader_src = "/kaggle/input/architect-scripts/asset_loader.py"
else:
    # Will be written inline
    loader_src = None

# Generate the combined bpy script
SCRIPT_PATH = "/tmp/enhanced_scene.py"

with open(SCRIPT_PATH, "w") as f:
    f.write(f"""
import bpy, math, os, json, random
from mathutils import Vector

# ═══════════════════════════════════════════════
# RESET
# ═══════════════════════════════════════════════
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# Color management
scene.view_settings.view_transform = 'Standard'
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0
scene.render.image_settings.color_mode = 'RGB'

ASSETS_DIR = "{ASSETS_DIR}"

# ═══════════════════════════════════════════════
# ASSET LOADER (inline)
# ═══════════════════════════════════════════════
def load_image(path, colorspace="sRGB"):
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = colorspace
    return img

def apply_pbr_material(obj, texture_dir, uv_scale=1.0):
    name = os.path.basename(texture_dir)
    def find_file(names):
        for n in names:
            for ext in [".jpg", ".png", ".jpeg", ".tif"]:
                p = os.path.join(texture_dir, n + ext)
                if os.path.exists(p): return p
        return None
    
    albedo = find_file(["albedo", "diffuse", "basecolor", "Color"])
    rough = find_file(["roughness", "rough", "Roughness"])
    normal = find_file(["normal", "nor_gl", "Normal", "NormalGL"])
    disp = find_file(["displacement", "disp", "Displacement", "Height"])
    ao = find_file(["ao", "AO", "ambient_occlusion"])
    
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    for n in nodes: nodes.remove(n)
    
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (400, 0)
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    
    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-800, 0)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-600, 0)
    mapping.inputs["Scale"].default_value = (uv_scale, uv_scale, uv_scale)
    links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])
    
    if albedo:
        t = nodes.new("ShaderNodeTexImage")
        t.location = (-400, 400)
        t.image = load_image(albedo, "sRGB")
        links.new(mapping.outputs["Vector"], t.inputs["Vector"])
        links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    
    if rough:
        t = nodes.new("ShaderNodeTexImage")
        t.location = (-400, 200)
        t.image = load_image(rough, "Non-Color")
        links.new(mapping.outputs["Vector"], t.inputs["Vector"])
        links.new(t.outputs["Color"], bsdf.inputs["Roughness"])
    
    if normal:
        t = nodes.new("ShaderNodeTexImage")
        t.location = (-400, -100)
        t.image = load_image(normal, "Non-Color")
        links.new(mapping.outputs["Vector"], t.inputs["Vector"])
        nm = nodes.new("ShaderNodeNormalMap")
        nm.location = (-100, -100)
        links.new(t.outputs["Color"], nm.inputs["Color"])
        links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    
    if disp:
        t = nodes.new("ShaderNodeTexImage")
        t.location = (-400, -400)
        t.image = load_image(disp, "Non-Color")
        links.new(mapping.outputs["Vector"], t.inputs["Vector"])
        d = nodes.new("ShaderNodeDisplacement")
        d.location = (100, -400)
        d.inputs["Scale"].default_value = 0.02
        links.new(t.outputs["Color"], d.inputs["Height"])
        links.new(d.outputs["Displacement"], output.inputs["Displacement"])
        mat.cycles.displacement_method = 'BOTH'
    
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return mat

def setup_hdri(hdr_path, strength=1.0, rot_z=0.0):
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    
    tc = nodes.new("ShaderNodeTexCoord")
    tc.location = (-600, 0)
    mp = nodes.new("ShaderNodeMapping")
    mp.location = (-400, 0)
    mp.inputs["Rotation"].default_value = (0, 0, rot_z)
    links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    
    env = nodes.new("ShaderNodeTexEnvironment")
    env.location = (-200, 0)
    env.image = bpy.data.images.load(hdr_path)
    links.new(mp.outputs["Vector"], env.inputs["Vector"])
    
    bg = nodes.new("ShaderNodeBackground")
    bg.location = (0, 0)
    bg.inputs["Strength"].default_value = strength
    links.new(env.outputs["Color"], bg.inputs["Color"])
    
    out = nodes.new("ShaderNodeOutputWorld")
    out.location = (200, 0)
    links.new(bg.outputs["Background"], out.inputs["Surface"])

def import_glb(path, loc=(0,0,0), rot=(0,0,0), scl=(1,1,1)):
    before = set(bpy.data.objects)
    try:
        bpy.ops.import_scene.gltf(filepath=path)
    except Exception as e:
        print(f"Import error: {{e}}")
        return []
    after = set(bpy.data.objects)
    new = list(after - before)
    for o in new:
        o.location = loc
        o.rotation_euler = rot
        o.scale = scl
    return new

def mat(name, color, roughness=0.5, metallic=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return m

# ═══════════════════════════════════════════════
# FIND TEXTURES
# ═══════════════════════════════════════════════
def find_texture(category):
    tex_dir = os.path.join(ASSETS_DIR, "textures")
    if not os.path.exists(tex_dir): return None
    for d in os.listdir(tex_dir):
        if category.lower() in d.lower():
            return os.path.join(tex_dir, d)
    return None

def find_hdri(preference="sky"):
    hdri_dir = os.path.join(ASSETS_DIR, "hdris")
    if not os.path.exists(hdri_dir): return None
    for f in os.listdir(hdri_dir):
        if preference.lower() in f.lower():
            return os.path.join(hdri_dir, f)
    # Return first
    for f in os.listdir(hdri_dir):
        if f.endswith((".hdr", ".exr")):
            return os.path.join(hdri_dir, f)
    return None

def find_model(category):
    model_dir = os.path.join(ASSETS_DIR, "models")
    if not os.path.exists(model_dir): return None
    for f in os.listdir(model_dir):
        if category.lower() in f.lower() and f.endswith(".glb"):
            return os.path.join(model_dir, f)
    return None

# ═══════════════════════════════════════════════
# BUILDING GEOMETRY (from generate_building.py)
# ═══════════════════════════════════════════════
W = {args.width}
L = {args.length}
floors = {args.floors}
fH = 2.8
thick = 0.3
total_h = floors * fH

# Materials
brick_tex = find_texture("brick")
concrete_tex = find_texture("concrete")
wood_tex = find_texture("wood")
roof_tex = find_texture("roof")
plaster_tex = find_texture("plaster")
grass_tex = find_texture("grass")

facade_mat = mat("Facade", (0.85, 0.82, 0.78), 0.8)
roof_mat = mat("Roof", (0.35, 0.18, 0.12), 0.8)
floor_mat = mat("Floor", (0.75, 0.65, 0.5), 0.7)
door_mat = mat("Door", (0.35, 0.22, 0.12), 0.6)
glass_mat = mat("Glass", (0.7, 0.85, 0.95), 0.05, 0.0)
glass_mat.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.3

# Apply PBR if available
if brick_tex:
    facade_mat = None  # Will apply PBR directly to walls

# Foundation
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.15))
found = bpy.context.active_object
found.name = "Foundation"
found.scale = (W/2 + 0.3, L/2 + 0.3, 0.15)
found.data.materials.append(mat("Concrete", (0.5, 0.5, 0.5), 0.95))

if concrete_tex:
    apply_pbr_material(found, concrete_tex, uv_scale=0.5)

# Walls
for floor in range(floors):
    z_base = floor * fH
    z_center = z_base + fH / 2
    
    walls = [
        (f"Wall_F_{{floor}}", (-W/2, -L/2, z_center), (W/2, -L/2, z_center)),
        (f"Wall_B_{{floor}}", (-W/2, L/2, z_center), (W/2, L/2, z_center)),
        (f"Wall_L_{{floor}}", (-W/2, -L/2, z_center), (-W/2, L/2, z_center)),
        (f"Wall_R_{{floor}}", (W/2, -L/2, z_center), (W/2, L/2, z_center)),
    ]
    
    for name, start, end in walls:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.sqrt(dx*dx + dy*dy)
        angle = math.atan2(dy, dx)
        mx = (start[0] + end[0]) / 2
        my = (start[1] + end[1]) / 2
        
        bpy.ops.mesh.primitive_cube_add(size=1, location=(mx, my, z_center))
        wall = bpy.context.active_object
        wall.name = name
        wall.scale = (length/2, thick/2, fH/2)
        wall.rotation_euler.z = angle
        
        if brick_tex:
            apply_pbr_material(wall, brick_tex, uv_scale=0.3)
        elif plaster_tex:
            apply_pbr_material(wall, plaster_tex, uv_scale=0.3)
        else:
            wall.data.materials.append(facade_mat or mat("Facade", (0.85, 0.82, 0.78), 0.8))
    
    # Floor slab
    if floor > 0:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, z_base))
        slab = bpy.context.active_object
        slab.name = f"Slab_{{floor}}"
        slab.scale = (W/2, L/2, 0.1)
        slab.data.materials.append(floor_mat)

# Windows
n_win = 3
win_w = 1.2
win_h = 1.5
for floor in range(floors):
    z_base = floor * fH
    win_z = z_base + fH * 0.4
    for i in range(n_win):
        x = -W/2 + (i + 1) * W / (n_win + 1)
        for y in [-L/2 - thick/2 - 0.01, L/2 + thick/2 + 0.01]:
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, win_z))
            win = bpy.context.active_object
            win.name = f"Window_{{floor}}_{{i}}"
            win.scale = (win_w/2, 0.05, win_h/2)
            win.data.materials.append(glass_mat)

# Door
door_z = 1.1
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -L/2 - thick/2 - 0.01, door_z))
door = bpy.context.active_object
door.name = "Door"
door.scale = (0.5, 0.05, 1.1)
door.data.materials.append(door_mat)

# Roof (gabled)
verts = [
    (-W/2 - 0.3, -L/2 - 0.3, total_h),
    (W/2 + 0.3, -L/2 - 0.3, total_h),
    (W/2 + 0.3, L/2 + 0.3, total_h),
    (-W/2 - 0.3, L/2 + 0.3, total_h),
    (0, -L/2 - 0.3, total_h + 2.5),
    (0, L/2 + 0.3, total_h + 2.5),
]
faces = [(0, 1, 4), (2, 3, 5), (0, 3, 5, 4), (1, 2, 5, 4)]
mesh = bpy.data.meshes.new("RoofMesh")
mesh.from_pydata(verts, [], faces)
mesh.update()
roof_obj = bpy.data.objects.new("Roof", mesh)
bpy.context.collection.objects.link(roof_obj)

if roof_tex:
    apply_pbr_material(roof_obj, roof_tex, uv_scale=0.2)
else:
    roof_obj.data.materials.append(roof_mat)

# Ground
bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, -0.01))
ground = bpy.context.active_object
ground.name = "Ground"
if grass_tex:
    apply_pbr_material(ground, grass_tex, uv_scale=0.1)
else:
    ground.data.materials.append(mat("Grass", (0.15, 0.45, 0.1), 0.95))

# Fence
for (x, y, sx, sy) in [(0, -15, 15, 0.05), (0, 15, 15, 0.05), (-15, 0, 0.05, 15), (15, 0, 0.05, 15)]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, 0.5))
    f = bpy.context.active_object
    f.scale = (sx, sy, 0.5)
    f.data.materials.append(mat("Fence", (0.4, 0.3, 0.2), 0.6))

# Path
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -8, 0.02))
path = bpy.context.active_object
path.scale = (1, 4, 0.02)
if concrete_tex:
    apply_pbr_material(path, concrete_tex, uv_scale=0.5)
else:
    path.data.materials.append(mat("Path", (0.6, 0.5, 0.4), 0.7))

# ═══════════════════════════════════════════════
# HDRI LIGHTING
# ═══════════════════════════════════════════════
hdri_path = find_hdri("sky")
if hdri_path:
    print(f"Using HDRI: {{hdri_path}}")
    setup_hdri(hdri_path, strength=1.0, rot_z=0.3)
else:
    print("No HDRI found, using world background")
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.5, 0.7, 1.0, 1.0)
    bg.inputs[1].default_value = 1.0

# ═══════════════════════════════════════════════
# CAMERA
# ═══════════════════════════════════════════════
if "{SCENE}" == "exterior":
    cam_loc = Vector((20, -20, 14))
    cam_target = Vector((0, 0, 1.5))
else:
    cam_loc = Vector((0, -L/2 + 2.5, 1.6))
    cam_target = Vector((0, L/2, 1.5))

bpy.ops.object.camera_add(location=cam_loc)
cam = bpy.context.active_object
cam.data.lens = 35
direction = cam_target - cam_loc
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
scene.camera = cam

# ═══════════════════════════════════════════════
# FURNITURE (if models available)
# ═══════════════════════════════════════════════
if "{SCENE}" == "interior" and os.path.exists(os.path.join(ASSETS_DIR, "models")):
    models_dir = os.path.join(ASSETS_DIR, "models")
    
    for cat in ["sofa", "table", "chair", "bed", "shelf", "lamp", "plant"]:
        model_path = find_model(cat)
        if model_path:
            if cat == "sofa":
                import_glb(model_path, loc=(0, -L/2 + 0.7, 0), rot=(0, 0, 3.14))
            elif cat == "table":
                import_glb(model_path, loc=(0, 0, 0))
            elif cat == "chair":
                import_glb(model_path, loc=(1.5, 0, 0), scl=(0.8, 0.8, 0.8))
            elif cat == "lamp":
                import_glb(model_path, loc=(W/2 - 0.5, -L/2 + 0.5, 0))
            elif cat == "plant":
                import_glb(model_path, loc=(W/2 - 0.5, L/2 - 0.5, 0))
            elif cat == "shelf":
                import_glb(model_path, loc=(-W/2 + 0.3, 0, 0), rot=(0, 0, 1.57))

# ═══════════════════════════════════════════════
# RENDER CONFIG
# ═══════════════════════════════════════════════
scene.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
for dev in ['OPTIX', 'CUDA']:
    try:
        prefs.compute_device_type = dev
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
            print(f"  {{dev}}: {{d.name}}")
        scene.cycles.device = 'GPU'
        break
    except: continue

scene.cycles.samples = {cfg['samples']}
scene.cycles.use_denoising = True
scene.render.resolution_x = {cfg['w'] if QUALITY == '4k' else cfg['w'] // cfg['tiles_x']}
scene.render.resolution_y = {cfg['h'] if QUALITY == '4k' else cfg['h'] // cfg['tiles_y']}
scene.render.resolution_percentage = 100

# ═══════════════════════════════════════════════
# COMPOSITOR (post-processing)
# ═══════════════════════════════════════════════
scene.use_nodes = True
tree = scene.node_tree
c_nodes = tree.nodes
c_links = tree.links
c_nodes.clear()

rl = c_nodes.new("CompositorNodeRLayers")
rl.location = (-400, 0)

glare = c_nodes.new("CompositorNodeGlare")
glare.glare_type = 'FOG_GLOW'
glare.threshold = 0.8
glare.size = 6
glare.location = (-100, 0)
c_links.new(rl.outputs["Image"], glare.inputs["Image"])

cb = c_nodes.new("CompositorNodeColorBalance")
cb.correction_method = 'LIFT_GAMMA_GAIN'
cb.lift = (0.95, 0.95, 1.05)
cb.gamma = (1.0, 1.02, 1.0)
cb.gain = (1.0, 1.0, 1.02)
cb.location = (200, 0)
c_links.new(glare.outputs["Image"], cb.inputs["Image"])

comp = c_nodes.new("CompositorNodeComposite")
comp.location = (500, 0)
c_links.new(cb.outputs["Image"], comp.inputs["Image"])

# ═══════════════════════════════════════════════
# RENDER
# ═══════════════════════════════════════════════
print(f"Objects: {{len(bpy.data.objects)}}")
print(f"Materials: {{len(bpy.data.materials)}}")

out_path = "/kaggle/working/architect_{SCENE}_{QUALITY}.png"
scene.render.filepath = out_path

import time as t
t0 = t.time()
bpy.ops.render.render(write_still=True)
elapsed = t.time() - t0

import os
if os.path.exists(out_path):
    sz = os.path.getsize(out_path) / 1024 / 1024
    print(f"\n✅ {{'{SCENE}'.upper()}} {{'{QUALITY}'.upper()}}: {{sz:.1f}} MB | {{elapsed:.0f}}s ({{elapsed/60:.1f}} min)")
else:
    print(f"\n❌ Render failed!")
""")

print(f"  Script: {SCRIPT_PATH}")

# ============================================================
# STEP 3: Run render
# ============================================================
print(f"\n[3/7] Rendering {SCENE} {QUALITY}...")

t0 = time.time()
r = subprocess.run(
    [BLENDER, "-b", "--python", SCRIPT_PATH],
    capture_output=True, text=True, timeout=3600
)
elapsed = time.time() - t0

for line in r.stdout.split('\n'):
    if any(k in line for k in ['GPU', 'CUDA', 'OPTIX', 'Render:', 'Objects:', 'Materials:', 'HDRI', 'Using', 'Error']):
        print(f"  {line.strip()}")

out_path = f"/kaggle/working/architect_{SCENE}_{QUALITY}.png"
if os.path.exists(out_path):
    sz = os.path.getsize(out_path) / 1024 / 1024
    print(f"\n✅ {SCENE.upper()} {QUALITY.upper()}: {sz:.1f} MB | {elapsed:.0f}s ({elapsed/60:.1f} min)")
else:
    print(f"\n❌ Failed!")
    print(f"stderr: {r.stderr[-500:]}")

# ============================================================
# Summary
# ============================================================
# Compliance check (if available)
if 'HAS_COMPLIANCE' in dir() and HAS_COMPLIANCE:
    print(f"\n[7/7] Compliance check...")
    checker = ComplianceChecker()
    building_params = {
        "floors": args.floors,
        "fH": 2.8,
        "W": args.width,
        "L": args.length,
        "rooms": [],
    }
    llm_params = {"building_type": "house", "style": args.style}
    result = checker.check_building(llm_params, building_params)
    print(f"  Score: {result.score:.2f}")
    print(f"  Passed: {result.passed}")
    for issue in result.issues:
        print(f"  ❌ {issue.code}: {issue.message}")
    for warn in result.warnings:
        print(f"  ⚠️ {warn.code}: {warn.message}")

print(f"\n{'='*60}")
print("OUTPUT:")
for f in sorted(os.listdir("/kaggle/working/")):
    if f.endswith(".png"):
        fpath = os.path.join("/kaggle/working/", f)
        sz = os.path.getsize(fpath) / 1024 / 1024
        print(f"  {f} — {sz:.1f} MB")
print(f"{'='*60}")
print("🎉 Done!")
