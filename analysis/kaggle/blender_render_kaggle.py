#!/usr/bin/env python3
"""
AI_Arhitector — Kaggle Blender 4.0 GPU Renderer

Blender 4.0.2 portable + OptiX/CUDA on Tesla P100 16GB.

Режимы:
  --quality 4k   (3840×2160, 256 samples)  — ~1.5 мин
  --quality 8k   (7680×4320, 256 samples)  — ~6 мин, 4 тайла
  --quality 16k  (15360×8640, 2048 samples) — ~18 мин, 12 тайлов

Запуск:
  python3 blender_render_kaggle.py --quality 4k
  python3 blender_render_kaggle.py --quality 8k
  python3 blender_render_kaggle.py --quality 16k
"""

import subprocess, os, time, sys, argparse, urllib.request, tarfile

# ============================================================
# CONFIG
# ============================================================
BLENDER_URL = "https://mirror.clarkson.edu/blender/release/Blender4.0/blender-4.0.2-linux-x64.tar.xz"
BLENDER_DIR = "/opt/blender4"
BLENDER = f"{BLENDER_DIR}/blender"
OUTPUT_DIR = "/kaggle/working"

CONFIGS = {
    "4k":  {"w": 3840,  "h": 2160,  "samples": 256,  "tiles_x": 1, "tiles_y": 1},
    "8k":  {"w": 7680,  "h": 4320,  "samples": 256,  "tiles_x": 2, "tiles_y": 2},
    "16k": {"w": 15360, "h": 8640,  "samples": 2048, "tiles_x": 4, "tiles_y": 3},
}

# ============================================================
# ARGS
# ============================================================
parser = argparse.ArgumentParser()
parser.add_argument("--quality", default="4k", choices=["4k", "8k", "16k"])
args = parser.parse_args()
QUALITY = args.quality
cfg = CONFIGS[QUALITY]
TILE_W = cfg["w"] // cfg["tiles_x"]
TILE_H = cfg["h"] // cfg["tiles_y"]

print("=" * 60)
print(f"AI_Arhitector — {QUALITY.upper()} Render")
print("=" * 60)
print(f"Resolution: {cfg['w']}×{cfg['h']}")
print(f"Samples: {cfg['samples']}")
if QUALITY != "4k":
    print(f"Tiles: {cfg['tiles_x']}×{cfg['tiles_y']} ({cfg['tiles_x']*cfg['tiles_y']} tiles)")

# ============================================================
# STEP 1: Install Blender 4.0.2
# ============================================================
print(f"\n[1/5] Blender 4.0.2...")
t0 = time.time()

if not os.path.exists(BLENDER):
    print("  Downloading...")
    tar_path = "/tmp/blender4.tar.xz"
    urllib.request.urlretrieve(BLENDER_URL, tar_path)
    print(f"  Download: {time.time()-t0:.0f}s")
    
    print("  Extracting...")
    with tarfile.open(tar_path) as tf:
        tf.extractall("/opt/")
    os.rename("/opt/blender-4.0.2-linux-x64", BLENDER_DIR)
    os.remove(tar_path)

r = subprocess.run([BLENDER, "--version"], capture_output=True, text=True, timeout=10)
version = r.stdout.strip().split('\n')[0]
print(f"  {version} ({time.time()-t0:.0f}s)")

# ============================================================
# STEP 2: GPU check
# ============================================================
print(f"\n[2/5] GPU...")
r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                   capture_output=True, text=True, timeout=10)
print(f"  {r.stdout.strip()}")

# ============================================================
# STEP 3: Load scene
# ============================================================
print(f"\n[3/5] Scene...")

# Check for custom bpy script in dataset
CUSTOM_SCRIPT = None
for dp in ["/kaggle/input/architect-bpy-scripts", "/kaggle/input"]:
    if os.path.exists(dp):
        for f in sorted(os.listdir(dp)):
            if f.endswith(".py") and "metadata" not in f and f != os.path.basename(__file__):
                CUSTOM_SCRIPT = os.path.join(dp, f)
                break
    if CUSTOM_SCRIPT:
        break

if CUSTOM_SCRIPT:
    print(f"  Custom: {CUSTOM_SCRIPT}")
else:
    print("  Built-in demo scene")
    CUSTOM_SCRIPT = "/tmp/demo_scene.py"
    with open(CUSTOM_SCRIPT, "w") as f:
        f.write(r"""
import bpy, math, random
from mathutils import Vector

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# Color management
scene.view_settings.view_transform = 'Standard'
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0
scene.render.image_settings.color_mode = 'RGB'

# World
world = bpy.data.worlds.new("World")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.5, 0.7, 1.0, 1.0)
bg.inputs[1].default_value = 1.0
scene.world = world

def mat(name, color, roughness=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs[0].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    return m

# Ground
bpy.ops.mesh.primitive_plane_add(size=50, location=(0, 0, 0))
bpy.context.active_object.data.materials.append(mat("Ground", (0.15, 0.45, 0.1), 0.9))

# House body
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 1.5))
h = bpy.context.active_object
h.scale = (6, 5, 1.5)
h.data.materials.append(mat("Wall", (0.85, 0.82, 0.78), 0.7))

# Roof
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 3.3))
r = bpy.context.active_object
r.scale = (6.5, 5.5, 0.2)
r.data.materials.append(mat("Roof", (0.35, 0.18, 0.12), 0.6))

# Windows
mat_glass = mat("Glass", (0.6, 0.8, 0.95), 0.1)
for x in [-2, 0, 2]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, -5.01, 1.5))
    bpy.context.active_object.scale = (0.8, 0.05, 0.8)
    bpy.context.active_object.data.materials.append(mat_glass)

# Door
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -5.01, 0.8))
d = bpy.context.active_object
d.scale = (0.7, 0.05, 0.8)
d.data.materials.append(mat("Door", (0.45, 0.28, 0.15), 0.4))

# Trees
for i in range(5):
    x = random.uniform(-14, 14)
    y = random.uniform(-14, 14)
    if abs(x) < 9 and abs(y) < 8: continue
    bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=3, location=(x, y, 1.5))
    bpy.context.active_object.data.materials.append(mat(f"T{i}", (0.35, 0.2, 0.1), 0.6))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.5, location=(x, y, 3.5))
    bpy.context.active_object.data.materials.append(mat(f"C{i}", (0.08, random.uniform(0.3,0.5), 0.05), 0.8))

# Camera
cam_loc = Vector((18, -18, 12))
bpy.ops.object.camera_add(location=cam_loc)
cam = bpy.context.active_object
cam.data.lens = 35
direction = Vector((0, 0, 1.5)) - cam_loc
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
scene.camera = cam

# Lights
bpy.ops.object.light_add(type='SUN', location=(8, -8, 20))
sun = bpy.context.active_object
sun.data.energy = 5.0
sun.rotation_euler = (math.radians(45), math.radians(15), 0)

bpy.ops.object.light_add(type='AREA', location=(-8, -5, 8))
fill = bpy.context.active_object
fill.data.energy = 200
fill.data.size = 8.0

print(f"Objects: {len(bpy.data.objects)}")
""")

# ============================================================
# STEP 4: Configure Cycles
# ============================================================
print(f"\n[4/5] Cycles GPU...")

cycles_cfg = f"""
import bpy
scene = bpy.context.scene
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
scene.render.resolution_x = {cfg['w'] if QUALITY == '4k' else TILE_W}
scene.render.resolution_y = {cfg['h'] if QUALITY == '4k' else TILE_H}
scene.render.resolution_percentage = 100
"""
cfg_path = "/tmp/cycles_cfg.py"
with open(cfg_path, "w") as f:
    f.write(cycles_cfg)

# ============================================================
# STEP 5: Render
# ============================================================
print(f"\n[5/5] Rendering {QUALITY.upper()}...")
total_start = time.time()

if QUALITY == "4k":
    # Single pass
    with open("/tmp/render_pass.py", "w") as f:
        f.write(f"""
import bpy, time
scene = bpy.context.scene
scene.render.filepath = "{OUTPUT_DIR}/architect_4k.png"
t0 = time.time()
bpy.ops.render.render(write_still=True)
print(f"  Render: {{time.time()-t0:.1f}}s")
""")

    r = subprocess.run(
        [BLENDER, "-b", "--python", CUSTOM_SCRIPT, "--python", cfg_path, "--python", "/tmp/render_pass.py"],
        capture_output=True, text=True, timeout=900
    )

    for line in r.stdout.split('\n'):
        if any(k in line for k in ['GPU', 'CUDA', 'OPTIX', 'Render:', 'Objects:', 'Error']):
            print(f"  {line.strip()}")

    out = f"{OUTPUT_DIR}/architect_4k.png"
    if os.path.exists(out):
        sz = os.path.getsize(out) / 1024 / 1024
        elapsed = time.time() - total_start
        print(f"\n✅ {QUALITY.upper()}: {sz:.1f} MB | {elapsed:.0f}s ({elapsed/60:.1f} min)")
    else:
        print(f"\n❌ Failed!")
        print(f"stderr: {r.stderr[-500:]}")

else:
    # Tiled render
    from PIL import Image

    tile_script = """
import bpy, time
scene = bpy.context.scene
scene.render.filepath = "{OUTPUT_DIR}/tile_{TX}_{TY}.png"

cam = scene.camera
if cam:
    cam.data.shift_x = {SHIFT_X}
    cam.data.shift_y = {SHIFT_Y}

t0 = time.time()
bpy.ops.render.render(write_still=True)
print(f"  Tile {TX},{TY}: {{time.time()-t0:.1f}}s")
"""

    final_img = Image.new('RGB', (cfg['w'], cfg['h']))

    for ty in range(cfg['tiles_y']):
        for tx in range(cfg['tiles_x']):
            idx = ty * cfg['tiles_x'] + tx + 1
            total = cfg['tiles_x'] * cfg['tiles_y']
            shift_x = (tx - (cfg['tiles_x'] - 1) / 2) / cfg['tiles_x']
            shift_y = (ty - (cfg['tiles_y'] - 1) / 2) / cfg['tiles_y']

            tile_py = f"/tmp/tile_{tx}_{ty}.py"
            with open(tile_py, "w") as f:
                f.write(tile_script.replace("{SHIFT_X}", str(shift_x))
                                   .replace("{SHIFT_Y}", str(shift_y))
                                   .replace("{TX}", str(tx))
                                   .replace("{TY}", str(ty))
                                   .replace("{OUTPUT_DIR}", OUTPUT_DIR))

            print(f"  Tile {idx}/{total} ({tx},{ty})...")
            r = subprocess.run(
                [BLENDER, "-b", "--python", CUSTOM_SCRIPT, "--python", cfg_path, "--python", tile_py],
                capture_output=True, text=True, timeout=600
            )

            tile_path = f"{OUTPUT_DIR}/tile_{tx}_{ty}.png"
            if os.path.exists(tile_path):
                tile_img = Image.open(tile_path)
                paste_x = tx * TILE_W
                paste_y = (cfg['tiles_y'] - 1 - ty) * TILE_H
                final_img.paste(tile_img, (paste_x, paste_y))
            else:
                print(f"    ⚠️ Tile not found!")

    out_path = f"{OUTPUT_DIR}/architect_{QUALITY}.png"
    final_img.save(out_path, "PNG")
    sz = os.path.getsize(out_path) / 1024 / 1024
    elapsed = time.time() - total_start
    print(f"\n✅ {QUALITY.upper()}: {sz:.1f} MB | {elapsed:.0f}s ({elapsed/60:.1f} min)")

# ============================================================
# Summary
# ============================================================
print(f"\n{'='*60}")
print("OUTPUT:")
for f in sorted(os.listdir(OUTPUT_DIR)):
    if f.endswith(".png"):
        fpath = os.path.join(OUTPUT_DIR, f)
        sz = os.path.getsize(fpath) / 1024 / 1024
        print(f"  {f} — {sz:.1f} MB")
print(f"{'='*60}")
print("🎉 Done!")
