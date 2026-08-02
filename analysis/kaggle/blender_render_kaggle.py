#!/usr/bin/env python3
"""
AI_Arhitector — Kaggle Blender Cycles GPU Renderer

Поддерживает три режима:
  - 4K  (3840×2160)  — ~2 мин, по умолчанию
  - 8K  (7680×4320)  — ~8 мин, 4 тайла
  - 16K (15360×8640) — ~18 мин, 12 тайлов

Использование:
  blender_render.py [--quality 4k|8k|16k]
"""

import subprocess, os, time, sys, argparse

print("=" * 60)
print("AI_Arhitector — Kaggle GPU Renderer")
print("=" * 60)

# Parse args
parser = argparse.ArgumentParser()
parser.add_argument("--quality", default="4k", choices=["4k", "8k", "16k"])
args = parser.parse_args()

QUALITY = args.quality

# Resolution config
CONFIGS = {
    "4k":  {"w": 3840,  "h": 2160,  "samples": 256,  "tiles_x": 1, "tiles_y": 1},
    "8k":  {"w": 7680,  "h": 4320,  "samples": 256,  "tiles_x": 2, "tiles_y": 2},
    "16k": {"w": 15360, "h": 8640,  "samples": 2048, "tiles_x": 4, "tiles_y": 3},
}
cfg = CONFIGS[QUALITY]
TILE_W = cfg["w"] // cfg["tiles_x"]
TILE_H = cfg["h"] // cfg["tiles_y"]

print(f"\nQuality: {QUALITY.upper()}")
print(f"Resolution: {cfg['w']}×{cfg['h']}")
print(f"Samples: {cfg['samples']}")
if QUALITY != "4k":
    print(f"Tiles: {cfg['tiles_x']}×{cfg['tiles_y']} = {cfg['tiles_x']*cfg['tiles_y']}")
    print(f"Tile size: {TILE_W}×{TILE_H}")

# Step 1: Install Blender
print(f"\n[1/5] Installing Blender...")
t0 = time.time()
subprocess.run(["apt-get", "update", "-qq"], capture_output=True, timeout=120)
subprocess.run(["apt-get", "install", "-y", "-qq", "blender"], capture_output=True, timeout=600)
print(f"  {time.time()-t0:.0f}s")

BLENDER = "/usr/bin/blender"
r = subprocess.run([BLENDER, "--version"], capture_output=True, text=True, timeout=10)
print(f"  {r.stdout.strip().split(chr(10))[0]}")

# Step 2: GPU check
print(f"\n[2/5] GPU...")
r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                   capture_output=True, text=True, timeout=10)
print(f"  {r.stdout.strip()}")

# Step 3: Load bpy script
print(f"\n[3/5] Loading scene...")

# Check for custom script in dataset
CUSTOM_SCRIPT = None
for dp in ["/kaggle/input/architect-bpy-scripts", "/kaggle/input"]:
    if os.path.exists(dp):
        for f in sorted(os.listdir(dp)):
            if f.endswith(".py") and f != "architect_16k_render.py":
                CUSTOM_SCRIPT = os.path.join(dp, f)
                break
    if CUSTOM_SCRIPT:
        break

if CUSTOM_SCRIPT:
    print(f"  Custom script: {CUSTOM_SCRIPT}")
else:
    print(f"  Using built-in demo scene")
    # Create demo scene
    CUSTOM_SCRIPT = "/tmp/demo_scene.py"
    with open(CUSTOM_SCRIPT, "w") as f:
        f.write(r"""
import bpy, math, random
from mathutils import Vector

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.view_settings.view_transform = 'Standard'
scene.render.film_transparent = False

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
    w = bpy.context.active_object
    w.scale = (0.8, 0.05, 0.8)
    w.data.materials.append(mat_glass)

# Door
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -5.01, 0.8))
d = bpy.context.active_object
d.scale = (0.7, 0.05, 0.8)
d.data.materials.append(mat("Door", (0.45, 0.28, 0.15), 0.4))

# Trees
for i in range(5):
    x = random.uniform(-14, 14)
    y = random.uniform(-14, 14)
    if abs(x) < 9 and abs(y) < 8:
        continue
    bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=3, location=(x, y, 1.5))
    bpy.context.active_object.data.materials.append(mat(f"Trunk{i}", (0.35, 0.2, 0.1), 0.6))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.5, location=(x, y, 3.5))
    bpy.context.active_object.data.materials.append(mat(f"Crown{i}", (0.08, random.uniform(0.3, 0.5), 0.05), 0.8))

# Camera
cam_loc = Vector((18, -18, 12))
cam_target = Vector((0, 0, 1.5))
bpy.ops.object.camera_add(location=cam_loc)
cam = bpy.context.active_object
cam.data.lens = 35
cam.data.clip_end = 1000
direction = cam_target - cam_loc
rot_quat = direction.to_track_quat('-Z', 'Y')
cam.rotation_euler = rot_quat.to_euler()
scene.camera = cam

# Sun
bpy.ops.object.light_add(type='SUN', location=(8, -8, 20))
sun = bpy.context.active_object
sun.data.energy = 5.0
sun.rotation_euler = (math.radians(45), math.radians(15), 0)

# Fill
bpy.ops.object.light_add(type='AREA', location=(-8, -5, 8))
fill = bpy.context.active_object
fill.data.energy = 100
fill.data.size = 8.0

print(f"Objects: {len(bpy.data.objects)}")
""")

# Step 4: Configure Cycles
print(f"\n[4/5] Configuring Cycles GPU...")
with open("/tmp/render_cfg.py", "w") as f:
    f.write(f"""
import bpy
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences

gpu_ok = False
for dev_type in ['OPTIX', 'CUDA']:
    try:
        prefs.compute_device_type = dev_type
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
            print(f"  {{dev_type}}: {{d.name}}")
        scene.cycles.device = 'GPU'
        gpu_ok = True
        break
    except:
        continue

if not gpu_ok:
    scene.cycles.device = 'CPU'
    print("  Using CPU")

scene.cycles.samples = {cfg['samples']}
scene.cycles.use_denoising = True
scene.render.resolution_x = {cfg['w'] if QUALITY == '4k' else TILE_W}
scene.render.resolution_y = {cfg['h'] if QUALITY == '4k' else TILE_H}
scene.render.resolution_percentage = 100
""")

# Step 5: Render
print(f"\n[5/5] Rendering {QUALITY.upper()}...")

if QUALITY == "4k":
    # Single pass render
    with open("/tmp/render_4k.py", "w") as f:
        f.write(r"""
import bpy, time
scene = bpy.context.scene
scene.render.filepath = "/kaggle/working/architect_4k.png"
t0 = time.time()
bpy.ops.render.render(write_still=True)
print(f"  Render: {time.time()-t0:.1f}s")
""")

    t0 = time.time()
    r = subprocess.run(
        [BLENDER, "-b", "--python", CUSTOM_SCRIPT, "--python", "/tmp/render_cfg.py", "--python", "/tmp/render_4k.py"],
        capture_output=True, text=True, timeout=900
    )
    elapsed = time.time() - t0

    for line in r.stdout.split('\n'):
        if any(k in line for k in ['GPU', 'CUDA', 'Render:', 'Error', 'Objects:', 'OPTIX']):
            print(f"  {line.strip()}")

    out = "/kaggle/working/architect_4k.png"
    if os.path.exists(out):
        sz = os.path.getsize(out) / 1024 / 1024
        print(f"\n✅ {QUALITY.upper()} output: {sz:.1f} MB")
        print(f"✅ Time: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    else:
        print(f"\n❌ No output!")

else:
    # Tiled render for 8K/16K
    from PIL import Image

    tile_script = f"""
import bpy, time
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
for dev_type in ['OPTIX', 'CUDA']:
    try:
        prefs.compute_device_type = dev_type
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scene.cycles.device = 'GPU'
        break
    except:
        continue
scene.cycles.samples = {cfg['samples']}
scene.cycles.use_denoising = True
scene.render.resolution_x = {TILE_W}
scene.render.resolution_y = {TILE_H}
scene.render.resolution_percentage = 100

cam = scene.camera
if cam:
    cam.data.shift_x = {{SHIFT_X}}
    cam.data.shift_y = {{SHIFT_Y}}

scene.render.filepath = "/kaggle/working/tile_{{TX}}_{{TY}}.png"
t0 = time.time()
bpy.ops.render.render(write_still=True)
print(f"  Tile {{TX}},{{TY}}: {{time.time()-t0:.1f}}s")
"""

    final_img = Image.new('RGB', (cfg['w'], cfg['h']))
    total_start = time.time()

    for ty in range(cfg['tiles_y']):
        for tx in range(cfg['tiles_x']):
            shift_x = (tx - (cfg['tiles_x'] - 1) / 2) / cfg['tiles_x']
            shift_y = (ty - (cfg['tiles_y'] - 1) / 2) / cfg['tiles_y']

            tile_py = f"/tmp/tile_{tx}_{ty}.py"
            with open(tile_py, "w") as f:
                f.write(tile_script.replace("{SHIFT_X}", str(shift_x))
                                   .replace("{SHIFT_Y}", str(shift_y))
                                   .replace("{TX}", str(tx))
                                   .replace("{TY}", str(ty)))

            print(f"  Tile {ty*cfg['tiles_x']+tx+1}/{cfg['tiles_x']*cfg['tiles_y']} ({tx},{ty})...")
            r = subprocess.run(
                [BLENDER, "-b", "--python", CUSTOM_SCRIPT, "--python", "/tmp/render_cfg.py", "--python", tile_py],
                capture_output=True, text=True, timeout=600
            )

            tile_path = f"/kaggle/working/tile_{tx}_{ty}.png"
            if os.path.exists(tile_path):
                tile_img = Image.open(tile_path)
                paste_x = tx * TILE_W
                paste_y = (cfg['tiles_y'] - 1 - ty) * TILE_H
                final_img.paste(tile_img, (paste_x, paste_y))

    elapsed = time.time() - total_start
    out_path = f"/kaggle/working/architect_{QUALITY}.png"
    final_img.save(out_path, "PNG")
    sz = os.path.getsize(out_path) / 1024 / 1024
    print(f"\n✅ {QUALITY.upper()} output: {sz:.1f} MB")
    print(f"✅ Time: {elapsed:.1f}s ({elapsed/60:.1f} min)")

# Summary
print(f"\n{'='*60}")
print("OUTPUT FILES:")
for f in sorted(os.listdir("/kaggle/working/")):
    if f.endswith(".png"):
        fpath = os.path.join("/kaggle/working/", f)
        sz = os.path.getsize(fpath) / 1024 / 1024
        print(f"  {f} — {sz:.1f} MB")
print(f"{'='*60}")
print("🎉 Done!")
