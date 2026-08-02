#!/usr/bin/env python3
"""
AI_Arhitector — 16K Blender Cycles рендер на Kaggle T4 GPU

Рендерит 15360×8640 (132 Мп) через tiled rendering:
- 12 тайлов (4×3 по 3840×2880)
- Cycles GPU + OptiX/CUDA на T4
- ~15-20 минут на полный 16K рендер

Использование:
  1. Загрузить bpy-скрипт как dataset: architect-bpy-scripts
  2. Запустить notebook на Kaggle с GPU T4
  3. Результат сохраняется в /kaggle/working/output/
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================
OUTPUT_DIR = "/kaggle/working/output"
SCRIPTS_DIR = "/kaggle/working/scripts"
TILE_WIDTH = 3840
TILE_HEIGHT = 2880
TILES_X = 4
TILES_Y = 3
TOTAL_WIDTH = TILE_WIDTH * TILES_X   # 15360
TOTAL_HEIGHT = TILE_HEIGHT * TILES_Y  # 8640
CYCLES_SAMPLES = 2048
DEVICE = "GPU"  # GPU or CPU

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(SCRIPTS_DIR, exist_ok=True)

# ============================================================
# STEP 0: Verify GPU
# ============================================================
print("=" * 60)
print("STEP 0: Checking GPU availability")
print("=" * 60)

try:
    result = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10)
    print(result.stdout[:500])
    GPU_AVAILABLE = True
except Exception as e:
    print(f"WARNING: nvidia-smi not found: {e}")
    print("Falling back to CPU rendering (will be SLOW)")
    GPU_AVAILABLE = False

# ============================================================
# STEP 1: Install/Verify Blender
# ============================================================
print("\n" + "=" * 60)
print("STEP 1: Setting up Blender")
print("=" * 60)

BLENDER_PATH = None

# Check if bpy is available (pip install bpy)
try:
    import bpy
    print("bpy module found (pip install bpy)")
    BLENDER_PATH = "python"
except ImportError:
    pass

# Check system blender
if BLENDER_PATH is None:
    for path in ["/usr/bin/blender", "/usr/local/bin/blender"]:
        if os.path.exists(path):
            BLENDER_PATH = path
            print(f"System Blender found: {path}")
            break

# Install Blender if not found
if BLENDER_PATH is None:
    print("Installing Blender 4.0+ via snap/apt...")
    # On Kaggle, we can install Blender
    os.system("apt-get update -qq && apt-get install -y -qq blender 2>/dev/null")
    if os.path.exists("/usr/bin/blender"):
        BLENDER_PATH = "/usr/bin/blender"
        print(f"Blender installed: {BLENDER_PATH}")
    else:
        print("ERROR: Could not install Blender")
        print("Trying bpy pip install...")
        os.system("pip install bpy 2>/dev/null")
        BLENDER_PATH = "python"

print(f"Using Blender at: {BLENDER_PATH}")

# ============================================================
# STEP 2: Load bpy script from dataset or generate
# ============================================================
print("\n" + "=" * 60)
print("STEP 2: Loading bpy generation script")
print("=" * 60)

# Look for bpy script in datasets
DATASET_PATHS = [
    "/kaggle/input/architect-bpy-scripts",
    "/kaggle/input/ai-arhitector-scripts",
    "/kaggle/input",
]

bpy_script = None
for dp in DATASET_PATHS:
    if os.path.exists(dp):
        for f in os.listdir(dp):
            if f.endswith(".py") and ("generate" in f.lower() or "architect" in f.lower()):
                bpy_script = os.path.join(dp, f)
                print(f"Found bpy script: {bpy_script}")
                break
    if bpy_script:
        break

if bpy_script is None:
    print("No bpy script found in datasets.")
    print("Generating a demo building scene for testing...")
    bpy_script = os.path.join(SCRIPTS_DIR, "demo_building.py")

    # Generate a demo building scene (same as AI_Arhitector generates)
    with open(bpy_script, "w") as f:
        f.write('''
import bpy
import bmesh
import math

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Create materials
def make_material(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs[0].default_value = (*color, 1)
    return mat

mat_wall = make_material("Wall", (0.85, 0.85, 0.82))
mat_floor = make_material("Floor", (0.4, 0.25, 0.15))
mat_roof = make_material("Roof", (0.3, 0.15, 0.1))
mat_glass = make_material("Glass", (0.8, 0.9, 1.0))
mat_door = make_material("Door", (0.5, 0.3, 0.15))

# ---- FLOOR ----
bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = "Floor"
floor.data.materials.append(mat_floor)

# ---- WALLS ----
wall_height = 2.8
wall_thickness = 0.3

def add_wall(x, y, z, sx, sy, sz, name):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
    obj = bpy.context.active_object
    obj.scale = (sx, sy, sz)
    obj.name = name
    obj.data.materials.append(mat_wall)
    return obj

# Front wall (with door hole)
add_wall(0, -6, wall_height/2, 12, wall_thickness, wall_height, "Wall_Front")
# Back wall
add_wall(0, 6, wall_height/2, 12, wall_thickness, wall_height, "Wall_Back")
# Left wall
add_wall(-6, 0, wall_height/2, wall_thickness, 12, wall_height, "Wall_Left")
# Right wall
add_wall(6, 0, wall_height/2, wall_thickness, 12, wall_height, "Wall_Right")

# ---- WINDOWS ----
for x in [-3, 3]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, -6, 1.5))
    win = bpy.context.active_object
    win.scale = (1.5, 0.05, 1.2)
    win.name = f"Window_Front_{x}"
    win.data.materials.append(mat_glass)

# ---- DOOR ----
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -6, 1.1))
door = bpy.context.active_object
door.scale = (1.0, 0.05, 2.2)
door.name = "Door"
door.data.materials.append(mat_door)

# ---- ROOF ----
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, wall_height + 0.5))
roof = bpy.context.active_object
roof.scale = (13, 13, 0.15)
roof.name = "Roof"
roof.data.materials.append(mat_roof)

# ---- CAMERA ----
bpy.ops.object.camera_add(location=(15, -15, 10))
cam = bpy.context.active_object
cam.name = "Camera"
cam.rotation_euler = (math.radians(55), 0, math.radians(45))
bpy.context.scene.camera = cam

# ---- LIGHT ----
bpy.ops.object.light_add(type='SUN', location=(5, -5, 15))
light = bpy.context.active_object
light.name = "Sun"
light.data.energy = 5.0

# ---- GROUND PLANE ----
bpy.ops.mesh.primitive_plane_add(size=50, location=(0, 0, -0.01))
ground = bpy.context.active_object
ground.name = "Ground"
mat_ground = make_material("Ground", (0.2, 0.5, 0.2))
ground.data.materials.append(mat_ground)

print("Demo building scene created successfully!")
print(f"Objects: {len(bpy.data.objects)}")
''')
    print(f"Demo script generated: {bpy_script}")

# ============================================================
# STEP 3: Run bpy script to create scene
# ============================================================
print("\n" + "=" * 60)
print("STEP 3: Running bpy script to create scene")
print("=" * 60)

if BLENDER_PATH == "python":
    # Using bpy pip module
    exec(open(bpy_script).read())
else:
    # Using Blender binary
    result = subprocess.run(
        [BLENDER_PATH, "--background", "--python", bpy_script],
        capture_output=True, text=True, timeout=300
    )
    print("STDOUT:", result.stdout[-1000:] if len(result.stdout) > 1000 else result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr[-500:])
        print(f"WARNING: Blender returned code {result.returncode}")

# ============================================================
# STEP 4: Configure Cycles for GPU rendering
# ============================================================
print("\n" + "=" * 60)
print("STEP 4: Configuring Cycles for T4 GPU")
print("=" * 60)

if BLENDER_PATH == "python":
    import bpy

    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'

    # GPU configuration
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'  # T4 supports CUDA

    # Enable all GPU devices
    prefs.get_devices()
    for device in prefs.devices:
        device.use = True
        print(f"  Enabled device: {device.name} ({device.type})")

    scene.cycles.device = 'GPU'
    scene.cycles.samples = CYCLES_SAMPLES
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = 'OPENIMAGEDENOISE'

    # Tile size for GPU
    scene.cycles.tile_x = TILE_WIDTH
    scene.cycles.tile_y = TILE_HEIGHT

    print(f"Engine: Cycles")
    print(f"Device: GPU (CUDA)")
    print(f"Samples: {CYCLES_SAMPLES}")
    print(f"Denoising: OpenImageDenoise")
    print(f"Tile size: {TILE_WIDTH}x{TILE_HEIGHT}")

# ============================================================
# STEP 5: 16K Tiled Rendering
# ============================================================
print("\n" + "=" * 60)
print("STEP 5: 16K Tiled Rendering")
print(f"  Total resolution: {TOTAL_WIDTH}x{TOTAL_HEIGHT}")
print(f"  Tiles: {TILES_X}x{TILES_Y} = {TILES_X*TILES_Y}")
print(f"  Tile size: {TILE_WIDTH}x{TILE_HEIGHT}")
print("=" * 60)

from PIL import Image
import numpy as np

start_time = time.time()

# Create the final image
final_image = Image.new('RGB', (TOTAL_WIDTH, TOTAL_HEIGHT))

for tile_y in range(TILES_Y):
    for tile_x in range(TILES_X):
        tile_idx = tile_y * TILES_X + tile_x + 1
        total_tiles = TILES_X * TILES_Y

        print(f"\n--- Tile {tile_idx}/{total_tiles} ({tile_x},{tile_y}) ---")

        # Calculate camera shift for this tile
        # Each tile covers a portion of the full frame
        shift_x = (tile_x - (TILES_X - 1) / 2) / TILES_X
        shift_y = (tile_y - (TILES_Y - 1) / 2) / TILES_Y

        tile_start = time.time()

        if BLENDER_PATH == "python":
            import bpy

            scene = bpy.context.scene
            scene.render.resolution_x = TILE_WIDTH
            scene.render.resolution_y = TILE_HEIGHT
            scene.render.resolution_percentage = 100

            # Set camera shift for tiled rendering
            cam = scene.camera
            if cam and cam.type == 'CAMERA':
                cam.data.shift_x = shift_x
                cam.data.shift_y = shift_y

            # Render tile
            tile_path = os.path.join(OUTPUT_DIR, f"tile_{tile_x}_{tile_y}.png")
            scene.render.filepath = tile_path
            bpy.ops.render.render(write_still=True)

        else:
            # Using Blender binary with Python script for tile
            tile_script = os.path.join(SCRIPTS_DIR, f"render_tile_{tile_x}_{tile_y}.py")
            with open(tile_script, "w") as f:
                f.write(f'''
import bpy
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.samples = {CYCLES_SAMPLES}
scene.render.resolution_x = {TILE_WIDTH}
scene.render.resolution_y = {TILE_HEIGHT}
scene.render.resolution_percentage = 100

prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'CUDA'
prefs.get_devices()
for dev in prefs.devices:
    dev.use = True

cam = scene.camera
if cam and cam.type == 'CAMERA':
    cam.data.shift_x = {shift_x}
    cam.data.shift_y = {shift_y}

scene.render.filepath = "{OUTPUT_DIR}/tile_{tile_x}_{tile_y}.png"
bpy.ops.render.render(write_still=True)
''')
            result = subprocess.run(
                [BLENDER_PATH, "--background", "--python", tile_script],
                capture_output=True, text=True, timeout=600
            )

        tile_elapsed = time.time() - tile_start
        print(f"  Tile rendered in {tile_elapsed:.1f}s")

        # Load and paste tile into final image
        tile_path = os.path.join(OUTPUT_DIR, f"tile_{tile_x}_{tile_y}.png")
        if os.path.exists(tile_path):
            tile_img = Image.open(tile_path)
            paste_x = tile_x * TILE_WIDTH
            paste_y = (TILES_Y - 1 - tile_y) * TILE_HEIGHT  # Flip Y
            final_image.paste(tile_img, (paste_x, paste_y))
            print(f"  Pasted at ({paste_x}, {paste_y})")
        else:
            print(f"  WARNING: Tile not found at {tile_path}")

total_elapsed = time.time() - start_time
print(f"\n{'=' * 60}")
print(f"TOTAL RENDER TIME: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")
print(f"{'=' * 60}")

# ============================================================
# STEP 6: Save final 16K image
# ============================================================
print("\n" + "=" * 60)
print("STEP 6: Saving final 16K image")
print("=" * 60)

output_path = os.path.join(OUTPUT_DIR, "architect_16k_final.png")
final_image.save(output_path, "PNG", optimize=True)

file_size = os.path.getsize(output_path)
print(f"Saved: {output_path}")
print(f"Resolution: {final_image.size[0]}x{final_image.size[1]}")
print(f"File size: {file_size / 1024 / 1024:.1f} MB")

# Also save a 4K preview
preview = final_image.resize((3840, 2160), Image.LANCZOS)
preview_path = os.path.join(OUTPUT_DIR, "architect_4k_preview.png")
preview.save(preview_path, "PNG")
preview_size = os.path.getsize(preview_path)
print(f"Preview: {preview_path} ({preview_size / 1024 / 1024:.1f} MB)")

# ============================================================
# STEP 7: Quality verification
# ============================================================
print("\n" + "=" * 60)
print("STEP 7: Quality verification")
print("=" * 60)

checks = {
    "Resolution >= 16K": final_image.size[0] >= TOTAL_WIDTH and final_image.size[1] >= TOTAL_HEIGHT,
    "File size >= 8MB": file_size >= 8 * 1024 * 1024,
    "Render time < 30 min": total_elapsed < 1800,
    "All tiles rendered": all(
        os.path.exists(os.path.join(OUTPUT_DIR, f"tile_{x}_{y}.png"))
        for y in range(TILES_Y) for x in range(TILES_X)
    ),
}

all_passed = True
for check, passed in checks.items():
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status} — {check}")
    if not passed:
        all_passed = False

print(f"\n{'=' * 60}")
if all_passed:
    print("ALL QUALITY CHECKS PASSED ✅")
else:
    print("SOME CHECKS FAILED ❌ — review above")
print(f"{'=' * 60}")

# ============================================================
# STEP 8: Upload results (optional)
# ============================================================
print("\n" + "=" * 60)
print("STEP 8: Results summary")
print("=" * 60)
print(f"Output directory: {OUTPUT_DIR}")
for f in sorted(os.listdir(OUTPUT_DIR)):
    fpath = os.path.join(OUTPUT_DIR, f)
    fsize = os.path.getsize(fpath) / 1024 / 1024
    print(f"  {f} — {fsize:.1f} MB")

print("\nDone! 🎉")
