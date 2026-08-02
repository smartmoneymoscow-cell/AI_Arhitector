
import bpy
import math

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Materials
def make_material(name, color, roughness=0.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs[0].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    return mat

mat_wall = make_material("Wall", (0.92, 0.90, 0.85), 0.8)
mat_floor = make_material("Floor", (0.55, 0.35, 0.2), 0.6)
mat_ceiling = make_material("Ceiling", (0.95, 0.95, 0.95), 0.9)
mat_wood = make_material("Wood", (0.45, 0.28, 0.15), 0.4)
mat_fabric = make_material("Fabric", (0.3, 0.35, 0.5), 0.8)
mat_metal = make_material("Metal", (0.7, 0.7, 0.72), 0.2)
mat_glass = make_material("Glass", (0.8, 0.9, 0.95), 0.05)

# Room dimensions (living room)
W, D, H = 6, 5, 2.8
wall_t = 0.15

# ---- FLOOR ----
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
floor = bpy.context.active_object
floor.scale = (W/2, D/2, 1)
floor.name = "Floor"
floor.data.materials.append(mat_floor)

# ---- CEILING ----
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, H))
ceil = bpy.context.active_object
ceil.scale = (W/2, D/2, 1)
ceil.name = "Ceiling"
ceil.data.materials.append(mat_ceiling)

# ---- WALLS ----
for (x, y, sx, sy, name) in [
    (0, -D/2, W/2, wall_t, "Wall_Front"),
    (0, D/2, W/2, wall_t, "Wall_Back"),
    (-W/2, 0, wall_t, D/2, "Wall_Left"),
    (W/2, 0, wall_t, D/2, "Wall_Right"),
]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, H/2))
    wall = bpy.context.active_object
    wall.scale = (sx, sy, H/2)
    wall.name = name
    wall.data.materials.append(mat_wall)

# ---- WINDOW (front wall) ----
bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.5, -D/2 - 0.01, 1.5))
win1 = bpy.context.active_object
win1.scale = (1.2, 0.05, 1.0)
win1.name = "Window_1"
win1.data.materials.append(mat_glass)

bpy.ops.mesh.primitive_cube_add(size=1, location=(1.5, -D/2 - 0.01, 1.5))
win2 = bpy.context.active_object
win2.scale = (1.2, 0.05, 1.0)
win2.name = "Window_2"
win2.data.materials.append(mat_glass)

# ---- SOFA ----
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -D/2 + 0.5, 0.25))
sofa_base = bpy.context.active_object
sofa_base.scale = (1.8, 0.5, 0.25)
sofa_base.name = "Sofa_Base"
sofa_base.data.materials.append(mat_fabric)

# Sofa back
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -D/2 + 0.15, 0.5))
sofa_back = bpy.context.active_object
sofa_back.scale = (1.8, 0.1, 0.25)
sofa_back.name = "Sofa_Back"
sofa_back.data.materials.append(mat_fabric)

# Sofa arms
for x in [-1.7, 1.7]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, -D/2 + 0.5, 0.35))
    arm = bpy.context.active_object
    arm.scale = (0.1, 0.5, 0.15)
    arm.name = f"Sofa_Arm_{x}"
    arm.data.materials.append(mat_fabric)

# ---- COFFEE TABLE ----
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.2))
table_top = bpy.context.active_object
table_top.scale = (0.6, 0.35, 0.03)
table_top.name = "CoffeeTable_Top"
table_top.data.materials.append(mat_wood)

# Table legs
for (lx, ly) in [(-0.5, -0.25), (-0.5, 0.25), (0.5, -0.25), (0.5, 0.25)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=0.37, location=(lx, ly, 0.185))
    leg = bpy.context.active_object
    leg.name = "TableLeg"
    leg.data.materials.append(mat_metal)

# ---- BOOKSHELF (back wall) ----
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, D/2 - 0.2, 0.9))
shelf = bpy.context.active_object
shelf.scale = (1.5, 0.25, 0.9)
shelf.name = "Bookshelf"
shelf.data.materials.append(mat_wood)

# Books on shelf
for i in range(8):
    bx = -0.6 + i * 0.17
    bpy.ops.mesh.primitive_cube_add(size=1, location=(bx, D/2 - 0.2, 0.5 + (i % 3) * 0.25))
    book = bpy.context.active_object
    book.scale = (0.06, 0.15, 0.1)
    book.name = f"Book_{i}"
    colors = [(0.7,0.1,0.1), (0.1,0.3,0.7), (0.1,0.6,0.3), (0.8,0.6,0.1)]
    book.data.materials.append(make_material(f"BookMat_{i}", colors[i % 4]))

# ---- TV (on wall) ----
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, D/2 - 0.05, 1.8))
tv = bpy.context.active_object
tv.scale = (1.0, 0.03, 0.55)
tv.name = "TV"
mat_screen = make_material("Screen", (0.05, 0.05, 0.08), 0.1)
tv.data.materials.append(mat_screen)

# ---- RUG ----
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, -0.5, 0.01))
rug = bpy.context.active_object
rug.scale = (1.5, 1.0, 1)
rug.name = "Rug"
mat_rug = make_material("Rug", (0.6, 0.45, 0.3), 0.9)
rug.data.materials.append(mat_rug)

# ---- FLOOR LAMP ----
bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=1.5, location=(1.8, -D/2 + 0.8, 0.75))
lamp_pole = bpy.context.active_object
lamp_pole.name = "LampPole"
lamp_pole.data.materials.append(mat_metal)

bpy.ops.mesh.primitive_cone_add(radius1=0.2, radius2=0.05, depth=0.3, location=(1.8, -D/2 + 0.8, 1.6))
lamp_shade = bpy.context.active_object
lamp_shade.name = "LampShade"
mat_shade = make_material("Shade", (0.9, 0.85, 0.7), 0.8)
lamp_shade.data.materials.append(mat_shade)

# ---- CAMERA (inside room, looking at sofa) ----
bpy.ops.object.camera_add(location=(0, -D/2 + 2.5, 1.6))
cam = bpy.context.active_object
cam.name = "Camera"
cam.rotation_euler = (math.radians(85), 0, 0)
bpy.context.scene.camera = cam

# ---- LIGHTING ----
# Main ceiling light
bpy.ops.object.light_add(type='AREA', location=(0, 0, H - 0.1))
main_light = bpy.context.active_object
main_light.name = "CeilingLight"
main_light.data.energy = 300
main_light.data.size = 1.5

# Window light (simulating daylight)
bpy.ops.object.light_add(type='AREA', location=(-1.5, -D/2, 1.5))
win_light = bpy.context.active_object
win_light.name = "WindowLight"
win_light.data.energy = 150
win_light.data.size = 2.0
win_light.rotation_euler = (math.radians(90), 0, 0)

# Accent light
bpy.ops.object.light_add(type='POINT', location=(0, -D/2 + 0.5, 2.0))
accent = bpy.context.active_object
accent.name = "AccentLight"
accent.data.energy = 50

print("Interior living room scene created!")
print(f"Objects: {len(bpy.data.objects)}")
print(f"Materials: {len(bpy.data.materials)}")
