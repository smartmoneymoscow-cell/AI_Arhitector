"""
ArchAI — Blender Building Generator
Generates architectural 3D models from JSON parameters.
Based on BlenderLLM approach + custom architectural logic.

Usage:
    blender --background --python generate_building.py -- params.json output.glb

Or from Blender script editor:
    import json, bpy, sys
    sys.argv = ['--', json.dumps(params), 'output.glb']
    exec(open('generate_building.py').read())
"""

import json
import math
import os
import sys

import bpy

# ═══════════════════════════════════════════════════════════════
# DEFAULT PARAMETERS
# ═══════════════════════════════════════════════════════════════
DEFAULTS = {
    "type": "house",
    "floors": 2,
    "width": 10,
    "length": 12,
    "floor_height": 3.0,
    "wall_thickness": 0.3,
    "roof_type": "gabled",  # gabled | hip | flat
    "roof_height": 2.5,
    "facade_material": "plaster",  # brick | wood | glass | plaster | stone
    "facade_color": "#e8e0d4",
    "roof_color": "#8b4513",
    "has_balcony": False,
    "has_terrace": False,
    "has_garage": False,
    "has_basement": False,
    "windows_per_floor": 3,
    "window_width": 1.2,
    "window_height": 1.5,
    "door_width": 1.0,
    "door_height": 2.2,
    "rooms": [],
    "style": "modern",
}


# ═══════════════════════════════════════════════════════════════
# MATERIALS
# ═══════════════════════════════════════════════════════════════
def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def create_material(name, color_hex, roughness=0.8, metallic=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        r, g, b = hex_to_rgb(color_hex)
        bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


def get_facade_material(params):
    mat_name = f"Facade_{params['facade_material']}"
    existing = bpy.data.materials.get(mat_name)
    if existing:
        return existing

    mats = {
        "brick": ("#b5651d", 0.9, 0.0),
        "wood": ("#8b6914", 0.7, 0.0),
        "glass": ("#87ceeb", 0.1, 0.3),
        "plaster": (params.get("facade_color", "#e8e0d4"), 0.85, 0.0),
        "stone": ("#808080", 0.95, 0.0),
        "concrete": ("#a0a0a0", 0.9, 0.0),
    }
    color, rough, metal = mats.get(params["facade_material"], ("#e8e0d4", 0.85, 0.0))
    return create_material(mat_name, color, rough, metal)


def get_glass_material():
    mat = bpy.data.materials.get("Glass")
    if mat:
        return mat
    mat = bpy.data.materials.new(name="Glass")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.8, 0.9, 1.0, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.05
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["Transmission Weight"].default_value = 0.9
        bsdf.inputs["Alpha"].default_value = 0.3
    mat.blend_method = "BLEND" if hasattr(mat, "blend_method") else None
    return mat


# ═══════════════════════════════════════════════════════════════
# GEOMETRY BUILDERS
# ═══════════════════════════════════════════════════════════════
def create_box(name, location, dimensions, material=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (dimensions[0], dimensions[1], dimensions[2])
    bpy.ops.object.transform_apply(scale=True)
    if material:
        obj.data.materials.append(material)
    return obj


def create_wall(name, start, end, height, thickness, material=None):
    """Create a wall segment between two points."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.sqrt(dx * dx + dy * dy)
    angle = math.atan2(dy, dx)

    mid_x = (start[0] + end[0]) / 2
    mid_y = (start[1] + end[1]) / 2

    bpy.ops.mesh.primitive_cube_add(size=1, location=(mid_x, mid_y, height / 2))
    wall = bpy.context.active_object
    wall.name = name
    wall.scale = (length, thickness, height)
    wall.rotation_euler.z = angle
    bpy.ops.object.transform_apply(scale=True, rotation=True)

    if material:
        wall.data.materials.append(material)
    return wall


def cut_window(wall_obj, pos, width, height, glass_mat):
    """Add a window hole using boolean modifier."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=pos)
    cutter = bpy.context.active_object
    cutter.name = "window_cutter"
    cutter.scale = (width / 2, 0.5, height / 2)
    bpy.ops.object.transform_apply(scale=True)

    # Boolean difference
    mod = wall_obj.modifiers.new(name="Window", type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    bpy.context.view_layer.objects.active = wall_obj
    bpy.ops.object.modifier_apply(modifier="Window")

    # Glass pane
    bpy.ops.mesh.primitive_plane_add(size=1, location=pos)
    glass = bpy.context.active_object
    glass.name = "window_glass"
    glass.scale = (width, 0.02, height)
    glass.data.materials.append(glass_mat)
    bpy.context.view_layer.objects.active = glass
    bpy.ops.object.transform_apply(scale=True)

    bpy.data.objects.remove(cutter, do_unlink=True)
    return glass


# ═══════════════════════════════════════════════════════════════
# BUILDING GENERATORS
# ═══════════════════════════════════════════════════════════════
def generate_building(params):
    """Main building generation function."""
    W = params["width"]
    L = params["length"]
    fH = params["floor_height"]
    thick = params["wall_thickness"]
    floors = params["floors"]
    roof_type = params["roof_type"]

    facade_mat = get_facade_material(params)
    glass_mat = get_glass_material()
    roof_mat = create_material("Roof", params.get("roof_color", "#8b4513"), 0.85, 0.0)
    floor_mat = create_material("Floor", "#d4c5a9", 0.8, 0.0)

    all_objects = []
    total_h = floors * fH

    # ── Foundation ──
    foundation = create_box(
        "Foundation", (0, 0, -0.15), (W + 0.6, L + 0.6, 0.3), create_material("Concrete", "#808080", 0.95, 0.0)
    )
    all_objects.append(foundation)

    # ── Walls per floor ──
    for floor in range(floors):
        z_base = floor * fH
        z_center = z_base + fH / 2

        # 4 walls
        walls_data = [
            (f"Wall_F_{floor}", (-W / 2, -L / 2, z_center), (W / 2, -L / 2, z_center)),  # Front
            (f"Wall_B_{floor}", (-W / 2, L / 2, z_center), (W / 2, L / 2, z_center)),  # Back
            (f"Wall_L_{floor}", (-W / 2, -L / 2, z_center), (-W / 2, L / 2, z_center)),  # Left
            (f"Wall_R_{floor}", (W / 2, -L / 2, z_center), (W / 2, L / 2, z_center)),  # Right
        ]

        for name, start, end in walls_data:
            wall = create_wall(name, start, end, fH, thick, facade_mat)
            all_objects.append(wall)

        # ── Floor slab ──
        if floor > 0:
            slab = create_box(f"Slab_{floor}", (0, 0, z_base), (W, L, 0.2), floor_mat)
            all_objects.append(slab)

        # ── Windows ──
        n_win = params.get("windows_per_floor", 3)
        win_w = params.get("window_width", 1.2)
        win_h = params.get("window_height", 1.5)
        win_z = z_base + fH * 0.4

        # Front wall windows
        for i in range(n_win):
            x = -W / 2 + (i + 1) * W / (n_win + 1)
            pos = (x, -L / 2 - thick / 2, win_z)
            try:
                cut_window(bpy.data.objects.get(f"Wall_F_{floor}") or all_objects[-4], pos, win_w, win_h, glass_mat)
            except Exception:
                # Fallback: simple glass plane
                bpy.ops.mesh.primitive_plane_add(size=1, location=pos)
                g = bpy.context.active_object
                g.name = f"Window_F_{floor}_{i}"
                g.scale = (win_w, 0.02, win_h)
                g.data.materials.append(glass_mat)
                all_objects.append(g)

        # ── Balcony ──
        if params.get("has_balcony") and floor > 0:
            balc = create_box(f"Balcony_{floor}", (0, -L / 2 - 1.5, z_base + 0.05), (3, 1.5, 0.1), floor_mat)
            # Railing
            rail = create_box(f"Railing_{floor}", (0, -L / 2 - 2.2, z_base + 0.6), (3, 0.05, 1.0), facade_mat)
            all_objects.extend([balc, rail])

    # ── Door (front wall, ground floor) ──
    door_w = params.get("door_width", 1.0)
    door_h = params.get("door_height", 2.2)
    door_z = door_h / 2
    door_mat = create_material("Door", "#4a3728", 0.7, 0.0)
    door = create_box("Door", (0, -L / 2 - thick / 2, door_z), (door_w, 0.08, door_h), door_mat)
    all_objects.append(door)

    # ── Roof ──
    roof_h = params.get("roof_height", 2.5)
    if roof_type == "gabled":
        # A-frame roof
        verts = [
            (-W / 2 - 0.3, -L / 2 - 0.3, total_h),
            (W / 2 + 0.3, -L / 2 - 0.3, total_h),
            (W / 2 + 0.3, L / 2 + 0.3, total_h),
            (-W / 2 - 0.3, L / 2 + 0.3, total_h),
            (0, -L / 2 - 0.3, total_h + roof_h),
            (0, L / 2 + 0.3, total_h + roof_h),
        ]
        faces = [
            (0, 1, 4),  # Front slope
            (2, 3, 5),  # Back slope
            (0, 3, 5, 4),  # Left gable
            (1, 2, 5, 4),  # Right gable
        ]
        mesh = bpy.data.meshes.new("RoofMesh")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        roof_obj = bpy.data.objects.new("Roof", mesh)
        bpy.context.collection.objects.link(roof_obj)
        roof_obj.data.materials.append(roof_mat)
        all_objects.append(roof_obj)

    elif roof_type == "hip":
        # Hip roof (4 slopes)
        verts = [
            (-W / 2 - 0.3, -L / 2 - 0.3, total_h),
            (W / 2 + 0.3, -L / 2 - 0.3, total_h),
            (W / 2 + 0.3, L / 2 + 0.3, total_h),
            (-W / 2 - 0.3, L / 2 + 0.3, total_h),
            (0, 0, total_h + roof_h),
        ]
        faces = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
        mesh = bpy.data.meshes.new("HipRoofMesh")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        roof_obj = bpy.data.objects.new("Roof", mesh)
        bpy.context.collection.objects.link(roof_obj)
        roof_obj.data.materials.append(roof_mat)
        all_objects.append(roof_obj)

    elif roof_type == "flat":
        roof = create_box("Roof", (0, 0, total_h + 0.1), (W + 0.6, L + 0.6, 0.2), roof_mat)
        all_objects.append(roof)

    # ── Terrace ──
    if params.get("has_terrace"):
        terrace = create_box("Terrace", (W / 2 + 2, 0, 0.05), (3, L, 0.1), floor_mat)
        all_objects.append(terrace)

    # ── Garage ──
    if params.get("has_garage"):
        garage = create_box("Garage", (-W / 2 - 3, 0, 1.5), (4, 5, 3), facade_mat)
        garage_door = create_box("GarageDoor", (-W / 2 - 3, -2.5, 1.2), (3.5, 0.08, 2.4), door_mat)
        all_objects.extend([garage, garage_door])

    # ── Ground plane ──
    bpy.ops.mesh.primitive_plane_add(size=50, location=(0, 0, -0.01))
    ground = bpy.context.active_object
    ground.name = "Ground"
    ground_mat = create_material("Grass", "#4a7c3f", 0.95, 0.0)
    ground.data.materials.append(ground_mat)
    all_objects.append(ground)

    # ── Set world background ──
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.5, 0.7, 1.0, 1.0)
        bg.inputs["Strength"].default_value = 1.0

    return all_objects


# ═══════════════════════════════════════════════════════════════
# RENDER SETTINGS
# ═══════════════════════════════════════════════════════════════
def setup_render(engine="CYCLES", samples=128, resolution=1920):
    scene = bpy.context.scene
    scene.render.engine = engine
    scene.cycles.samples = samples
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"

    # Camera
    cam_data = bpy.data.cameras.new("Camera")
    cam_obj = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    # Position camera to see the building
    cam_obj.location = (20, -20, 15)
    cam_obj.rotation_euler = (math.radians(60), 0, math.radians(45))

    # Sun light
    sun_data = bpy.data.lights.new("Sun", type="SUN")
    sun_data.energy = 3
    sun_obj = bpy.data.objects.new("Sun", sun_data)
    scene.collection.objects.link(sun_obj)
    sun_obj.rotation_euler = (math.radians(45), math.radians(15), math.radians(30))


def export_model(filepath, fmt="glb"):
    """Export the scene to various formats."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.export_scene.gltf(filepath=filepath, export_format="GLB")
    elif ext == ".fbx":
        bpy.ops.export_scene.fbx(filepath=filepath)
    elif ext == ".obj":
        bpy.ops.wm.obj_export(filepath=filepath)
    elif ext == ".blend":
        bpy.ops.wm.save_as_mainfile(filepath=filepath)
    elif ext in (".ifc", ".ifczip"):
        # IFC export requires BlenderBIM addon
        try:
            bpy.ops.export_ifc.bim(filepath=filepath)
        except Exception:
            print("IFC export requires BlenderBIM addon. Exporting as .blend instead.")
            bpy.ops.wm.save_as_mainfile(filepath=filepath.replace(ext, ".blend"))


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    # Parse args
    args = sys.argv
    if "--" in args:
        args = args[args.index("--") + 1 :]
    else:
        args = []

    if len(args) >= 1:
        if args[0].endswith(".json"):
            with open(args[0]) as f:
                params = json.load(f)
        else:
            params = json.loads(args[0])
    else:
        params = DEFAULTS

    # Merge with defaults
    for k, v in DEFAULTS.items():
        params.setdefault(k, v)

    output_path = args[1] if len(args) >= 2 else "output/building.glb"
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Clear scene
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    # Generate
    print(
        f"[ArchAI] Generating {params['type']}: {params['floors']} floors, "
        f"{params['width']}x{params['length']}m, {params['facade_material']}"
    )

    objects = generate_building(params)

    # Setup render
    setup_render()

    # Export
    export_model(output_path)
    print(f"[ArchAI] Exported to {output_path}")
    print(f"[ArchAI] Generated {len(objects)} objects")


if __name__ == "__main__":
    main()
