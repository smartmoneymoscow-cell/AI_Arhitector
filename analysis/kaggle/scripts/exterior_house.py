
import bpy
import math
import random

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Materials
def make_material(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs[0].default_value = (*color, 1)
    return mat

mat_wall = make_material("Wall", (0.85, 0.82, 0.78))
mat_roof = make_material("Roof", (0.35, 0.18, 0.12))
mat_glass = make_material("Glass", (0.7, 0.85, 0.95))
mat_door = make_material("Door", (0.45, 0.28, 0.15))
mat_floor = make_material("Floor", (0.4, 0.35, 0.3))
mat_ground = make_material("Ground", (0.2, 0.45, 0.15))

# Dimensions
W, D, H = 12, 10, 5.6  # 2 floors x 2.8m
wall_t = 0.3

# ---- GROUND ----
bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, -0.01))
ground = bpy.context.active_object
ground.name = "Ground"
ground.data.materials.append(mat_ground)

# ---- FLOOR SLAB ----
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.05))
slab = bpy.context.active_object
slab.scale = (W/2 + 0.3, D/2 + 0.3, 0.05)
slab.name = "Foundation"
slab.data.materials.append(mat_floor)

# ---- WALLS ----
def add_wall(x, y, z, sx, sy, sz, name, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
    obj = bpy.context.active_object
    obj.scale = (sx, sy, sz)
    obj.name = name
    obj.data.materials.append(mat)
    return obj

# Outer walls
add_wall(0, -D/2, H/2, W/2, wall_t/2, H/2, "Wall_Front", mat_wall)
add_wall(0, D/2, H/2, W/2, wall_t/2, H/2, "Wall_Back", mat_wall)
add_wall(-W/2, 0, H/2, wall_t/2, D/2, H/2, "Wall_Left", mat_wall)
add_wall(W/2, 0, H/2, wall_t/2, D/2, H/2, "Wall_Right", mat_wall)

# Floor divider
add_wall(0, 0, 2.8, W/2, wall_t/2, 0.05, "Floor2_Slab", mat_floor)

# ---- WINDOWS (2 per floor, front) ----
for floor in range(2):
    for x_off in [-2.5, 2.5]:
        z = 2.8 * floor + 1.4
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x_off, -D/2 - 0.01, z))
        win = bpy.context.active_object
        win.scale = (1.2, 0.05, 1.0)
        win.name = f"Window_F{floor}_{x_off}"
        win.data.materials.append(mat_glass)

# Side windows
for floor in range(2):
    z = 2.8 * floor + 1.4
    for side in [-1, 1]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(side * W/2 + 0.01 * side, 0, z))
        win = bpy.context.active_object
        win.scale = (0.05, 1.0, 1.0)
        win.name = f"Window_Side_F{floor}_{side}"
        win.data.materials.append(mat_glass)

# ---- DOOR ----
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -D/2 - 0.01, 1.1))
door = bpy.context.active_object
door.scale = (0.9, 0.05, 1.1)
door.name = "Door"
door.data.materials.append(mat_door)

# ---- PORCH ----
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -D/2 - 1.0, 0.1))
porch = bpy.context.active_object
porch.scale = (2.0, 1.0, 0.1)
porch.name = "Porch"
porch.data.materials.append(mat_floor)

# Steps
for i in range(3):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -D/2 - 1.5 - i*0.3, 0.05 * (3-i)))
    step = bpy.context.active_object
    step.scale = (1.5, 0.15, 0.05)
    step.name = f"Step_{i}"

# ---- ROOF ----
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, H + 0.3))
roof = bpy.context.active_object
roof.scale = (W/2 + 1.0, D/2 + 1.0, 0.15)
roof.name = "Roof_Flat"
roof.data.materials.append(mat_roof)

# Roof edge
for (x, y, sx, sy) in [
    (0, -D/2 - 0.5, W/2 + 1.0, 0.1),
    (0, D/2 + 0.5, W/2 + 1.0, 0.1),
    (-W/2 - 0.5, 0, 0.1, D/2 + 1.0),
    (W/2 + 0.5, 0, 0.1, D/2 + 1.0),
]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, H + 0.5))
    edge = bpy.context.active_object
    edge.scale = (sx, sy, 0.2)
    edge.name = "Roof_Edge"
    edge.data.materials.append(mat_roof)

# ---- CHIMNEY ----
bpy.ops.mesh.primitive_cube_add(size=1, location=(3.5, 2.0, H + 1.2))
chimney = bpy.context.active_object
chimney.scale = (0.4, 0.4, 1.0)
chimney.name = "Chimney"
chimney.data.materials.append(mat_wall)

# ---- FENCE ----
fence_h = 1.2
for (x, y, sx, sy) in [
    (0, -15, 15, 0.05),
    (0, 15, 15, 0.05),
    (-15, 0, 0.05, 15),
    (15, 0, 0.05, 15),
]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, fence_h/2))
    fence = bpy.context.active_object
    fence.scale = (sx, sy, fence_h/2)
    fence.name = "Fence"

# ---- TREES ----
for i in range(6):
    x = random.uniform(-12, 12)
    y = random.uniform(-12, 12)
    if abs(x) < 8 and abs(y) < 7:
        continue  # Skip if too close to house
    
    # Trunk
    bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=3, location=(x, y, 1.5))
    trunk = bpy.context.active_object
    trunk.name = f"Tree_Trunk_{i}"
    mat_trunk = make_material(f"Trunk_{i}", (0.35, 0.2, 0.1))
    trunk.data.materials.append(mat_trunk)
    
    # Crown
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.5, location=(x, y, 3.8))
    crown = bpy.context.active_object
    crown.name = f"Tree_Crown_{i}"
    mat_crown = make_material(f"Crown_{i}", (0.08, random.uniform(0.25, 0.45), 0.05))
    crown.data.materials.append(mat_crown)

# ---- CAMERA ----
bpy.ops.object.camera_add(location=(18, -18, 12))
cam = bpy.context.active_object
cam.name = "Camera"
cam.rotation_euler = (math.radians(58), 0, math.radians(45))
bpy.context.scene.camera = cam

# ---- LIGHTING ----
bpy.ops.object.light_add(type='SUN', location=(8, -8, 20))
sun = bpy.context.active_object
sun.name = "Sun"
sun.data.energy = 5.0
sun.rotation_euler = (math.radians(45), math.radians(15), 0)

# Fill light
bpy.ops.object.light_add(type='AREA', location=(-5, -8, 8))
fill = bpy.context.active_object
fill.name = "FillLight"
fill.data.energy = 50
fill.data.size = 5.0

print("Exterior house scene created!")
print(f"Objects: {len(bpy.data.objects)}")
print(f"Materials: {len(bpy.data.materials)}")
