"""
ArchAI — Blender Interior Renderer
Generates photorealistic interior design renders.
Inspired by BlenderProc pipeline.

Usage:
    blender --background --python render_interior.py -- params.json output.png
"""

import json
import math
import os
import sys

import bpy

# ═══════════════════════════════════════════════════════════════
# INTERIOR STYLE PRESETS
# ═══════════════════════════════════════════════════════════════
STYLE_PRESETS = {
    "modern": {
        "wall_color": "#f5f5f5",
        "floor_color": "#c4a882",
        "ceiling_color": "#ffffff",
        "accent_color": "#2c3e50",
        "furniture_style": "minimalist",
        "light_temp": 5500,
    },
    "classic": {
        "wall_color": "#f0e6d3",
        "floor_color": "#8b6914",
        "ceiling_color": "#fffef7",
        "accent_color": "#8b0000",
        "furniture_style": "classic",
        "light_temp": 4000,
    },
    "scandinavian": {
        "wall_color": "#fafafa",
        "floor_color": "#d4b896",
        "ceiling_color": "#ffffff",
        "accent_color": "#8fbc8f",
        "furniture_style": "nordic",
        "light_temp": 5000,
    },
    "loft": {
        "wall_color": "#a0a0a0",
        "floor_color": "#6b6b6b",
        "ceiling_color": "#808080",
        "accent_color": "#ff6b35",
        "furniture_style": "industrial",
        "light_temp": 3500,
    },
    "minimalist": {
        "wall_color": "#ffffff",
        "floor_color": "#e0d8cc",
        "ceiling_color": "#ffffff",
        "accent_color": "#000000",
        "furniture_style": "ultra_minimal",
        "light_temp": 6000,
    },
}


# ═══════════════════════════════════════════════════════════════
# MATERIAL HELPERS
# ═══════════════════════════════════════════════════════════════
def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def make_material(name, color_hex, roughness=0.8, metallic=0.0, emission=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        r, g, b = hex_to_rgb(color_hex)
        bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if emission > 0:
            bsdf.inputs["Emission Color"].default_value = (r, g, b, 1.0)
            bsdf.inputs["Emission Strength"].default_value = emission
    return mat


def add_texture_to_material(mat, tex_type="wood", scale=1.0):
    """Add procedural texture to material."""
    mat.use_nodes = True
    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF")

    # Texture coordinate
    tex_coord = tree.nodes.new("ShaderNodeTexCoord")
    mapping = tree.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (scale, scale, scale)
    tree.links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])

    if tex_type == "wood":
        noise = tree.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 15.0
        noise.inputs["Detail"].default_value = 8.0
        tree.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        color_ramp = tree.nodes.new("ShaderNodeValToRGB")
        color_ramp.color_ramp.elements[0].color = (0.4, 0.25, 0.1, 1.0)
        color_ramp.color_ramp.elements[1].color = (0.7, 0.5, 0.25, 1.0)
        tree.links.new(noise.outputs["Fac"], color_ramp.inputs["Fac"])
        tree.links.new(color_ramp.outputs["Color"], bsdf.inputs["Base Color"])

    elif tex_type == "marble":
        voronoi = tree.nodes.new("ShaderNodeTexVoronoi")
        voronoi.inputs["Scale"].default_value = 3.0
        tree.links.new(mapping.outputs["Vector"], voronoi.inputs["Vector"])
        color_ramp = tree.nodes.new("ShaderNodeValToRGB")
        color_ramp.color_ramp.elements[0].color = (0.9, 0.88, 0.85, 1.0)
        color_ramp.color_ramp.elements[1].color = (0.7, 0.68, 0.65, 1.0)
        tree.links.new(voronoi.outputs["Distance"], color_ramp.inputs["Fac"])
        tree.links.new(color_ramp.outputs["Color"], bsdf.inputs["Base Color"])


# ═══════════════════════════════════════════════════════════════
# ROOM BUILDER
# ═══════════════════════════════════════════════════════════════
def build_room(width, length, height, style_preset):
    """Build a room with walls, floor, ceiling."""
    style = STYLE_PRESETS.get(style_preset, STYLE_PRESETS["modern"])
    objects = []

    wall_mat = make_material("Wall", style["wall_color"], 0.9)
    floor_mat = make_material("Floor", style["floor_color"], 0.6)
    ceiling_mat = make_material("Ceiling", style["ceiling_color"], 0.95)

    # Add wood texture to floor
    if style_preset in ("classic", "scandinavian", "modern"):
        add_texture_to_material(floor_mat, "wood", scale=0.5)

    # Floor
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "Floor"
    floor.scale = (width, length, 1)
    bpy.ops.object.transform_apply(scale=True)
    floor.data.materials.append(floor_mat)
    objects.append(floor)

    # Ceiling
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, height))
    ceiling = bpy.context.active_object
    ceiling.name = "Ceiling"
    ceiling.scale = (width, length, 1)
    ceiling.rotation_euler.x = math.pi
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    ceiling.data.materials.append(ceiling_mat)
    objects.append(ceiling)

    # Walls (4 sides)
    walls = [
        ("Wall_Front", (0, -length / 2, height / 2), (width, 0.15, height), (0, 0, 0)),
        ("Wall_Back", (0, length / 2, height / 2), (width, 0.15, height), (0, 0, 0)),
        ("Wall_Left", (-width / 2, 0, height / 2), (0.15, length, height), (0, 0, 0)),
        ("Wall_Right", (width / 2, 0, height / 2), (0.15, length, height), (0, 0, 0)),
    ]
    for name, loc, dims, rot in walls:
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
        w = bpy.context.active_object
        w.name = name
        w.scale = (dims[0] / 2, dims[1] / 2, dims[2] / 2)
        bpy.ops.object.transform_apply(scale=True)
        w.data.materials.append(wall_mat)
        objects.append(w)

    return objects, {"wall": wall_mat, "floor": floor_mat, "ceiling": ceiling_mat}


# ═══════════════════════════════════════════════════════════════
# FURNITURE GENERATORS
# ═══════════════════════════════════════════════════════════════
def add_sofa(location, color="#4a4a4a", width=2.0):
    """Generate a simple sofa."""
    mat = make_material("Sofa_Fabric", color, 0.85)
    objs = []

    # Seat
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    seat = bpy.context.active_object
    seat.name = "Sofa_Seat"
    seat.scale = (width / 2, 0.5, 0.3)
    bpy.ops.object.transform_apply(scale=True)
    seat.data.materials.append(mat)
    objs.append(seat)

    # Back
    bpy.ops.mesh.primitive_cube_add(size=1, location=(location[0], location[1] + 0.35, location[2] + 0.35))
    back = bpy.context.active_object
    back.name = "Sofa_Back"
    back.scale = (width / 2, 0.1, 0.35)
    bpy.ops.object.transform_apply(scale=True)
    back.data.materials.append(mat)
    objs.append(back)

    # Armrests
    for side in [-1, 1]:
        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(location[0] + side * (width / 2 - 0.1), location[1], location[2] + 0.2)
        )
        arm = bpy.context.active_object
        arm.name = f"Sofa_Arm_{'L' if side < 0 else 'R'}"
        arm.scale = (0.1, 0.5, 0.25)
        bpy.ops.object.transform_apply(scale=True)
        arm.data.materials.append(mat)
        objs.append(arm)

    return objs


def add_table(location, width=1.2, height=0.75, color="#8b6914"):
    """Generate a simple table."""
    mat = make_material("Table_Wood", color, 0.6)
    objs = []

    # Top
    bpy.ops.mesh.primitive_cube_add(size=1, location=(location[0], location[1], location[2] + height))
    top = bpy.context.active_object
    top.name = "Table_Top"
    top.scale = (width / 2, width * 0.6 / 2, 0.04)
    bpy.ops.object.transform_apply(scale=True)
    top.data.materials.append(mat)
    objs.append(top)

    # Legs
    for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=(
                location[0] + dx * (width / 2 - 0.08),
                location[1] + dy * (width * 0.6 / 2 - 0.08),
                location[2] + height / 2,
            ),
        )
        leg = bpy.context.active_object
        leg.name = "Table_Leg"
        leg.scale = (0.04, 0.04, height / 2)
        bpy.ops.object.transform_apply(scale=True)
        leg.data.materials.append(mat)
        objs.append(leg)

    return objs


def add_bed(location, width=1.8, length=2.0, color="#f0f0f0"):
    """Generate a simple bed."""
    mat = make_material("Bed_Sheet", color, 0.9)
    pillow_mat = make_material("Pillow", "#ffffff", 0.95)
    objs = []

    # Mattress
    bpy.ops.mesh.primitive_cube_add(size=1, location=(location[0], location[1], location[2] + 0.25))
    mattress = bpy.context.active_object
    mattress.name = "Mattress"
    mattress.scale = (width / 2, length / 2, 0.25)
    bpy.ops.object.transform_apply(scale=True)
    mattress.data.materials.append(mat)
    objs.append(mattress)

    # Headboard
    bpy.ops.mesh.primitive_cube_add(size=1, location=(location[0], location[1] + length / 2 - 0.05, location[2] + 0.6))
    hb = bpy.context.active_object
    hb.name = "Headboard"
    hb.scale = (width / 2, 0.05, 0.6)
    bpy.ops.object.transform_apply(scale=True)
    hb.data.materials.append(make_material("Headboard", "#3d2b1f", 0.7))
    objs.append(hb)

    # Pillows
    for side in [-1, 1]:
        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(location[0] + side * 0.3, location[1] + length / 2 - 0.3, location[2] + 0.55)
        )
        pillow = bpy.context.active_object
        pillow.name = "Pillow"
        pillow.scale = (0.25, 0.15, 0.08)
        bpy.ops.object.transform_apply(scale=True)
        pillow.data.materials.append(pillow_mat)
        objs.append(pillow)

    return objs


def add_chandelier(location, style="modern"):
    """Generate a simple chandelier/pendant light."""
    mat = make_material("Metal", "#333333", 0.3, 0.8)
    light_mat = make_material("Light_Emit", "#fff5e0", 0.5, 0.0, emission=5.0)
    objs = []

    # Wire
    bpy.ops.mesh.primitive_cylinder_add(radius=0.01, depth=1.0, location=(location[0], location[1], location[2] + 0.5))
    wire = bpy.context.active_object
    wire.name = "Chandelier_Wire"
    wire.data.materials.append(mat)
    objs.append(wire)

    # Shade
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2, location=location)
    shade = bpy.context.active_object
    shade.name = "Chandelier_Shade"
    shade.data.materials.append(light_mat)
    objs.append(shade)

    # Actual light
    light_data = bpy.data.lights.new("Chandelier_Light", type="POINT")
    light_data.energy = 500
    light_data.color = (1.0, 0.95, 0.85)
    light_obj = bpy.data.objects.new("Chandelier_Light", light_data)
    bpy.context.collection.objects.link(light_obj)
    light_obj.location = location
    objs.append(light_obj)

    return objs


# ═══════════════════════════════════════════════════════════════
# INTERIOR RENDERER
# ═══════════════════════════════════════════════════════════════
def setup_interior_camera(location, look_at, focal_length=35):
    cam_data = bpy.data.cameras.new("InteriorCam")
    cam_data.lens = focal_length
    cam_obj = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj
    cam_obj.location = location

    # Point camera at target
    direction = [look_at[i] - location[i] for i in range(3)]
    rot_x = -math.atan2(direction[2], math.sqrt(direction[0] ** 2 + direction[1] ** 2))
    rot_z = math.atan2(direction[1], direction[0])
    cam_obj.rotation_euler = (rot_x + math.pi / 2, 0, rot_z)
    return cam_obj


def setup_interior_lighting(style, room_width, room_length, height):
    """Setup natural + artificial lighting."""
    style_data = STYLE_PRESETS.get(style, STYLE_PRESETS["modern"])
    light_temp = style_data["light_temp"]

    # Window light (sun)
    sun_data = bpy.data.lights.new("Window_Light", type="SUN")
    sun_data.energy = 3
    sun_data.color = temp_to_rgb(light_temp)
    sun_obj = bpy.data.objects.new("Window_Light", sun_data)
    bpy.context.collection.objects.link(sun_obj)
    sun_obj.rotation_euler = (math.radians(50), math.radians(20), math.radians(-30))

    # Ambient area light
    area_data = bpy.data.lights.new("Ambient", type="AREA")
    area_data.energy = 200
    area_data.size = max(room_width, room_length)
    area_data.color = temp_to_rgb(light_temp)
    area_obj = bpy.data.objects.new("Ambient", area_data)
    bpy.context.collection.objects.link(area_obj)
    area_obj.location = (0, 0, height - 0.2)


def temp_to_rgb(kelvin):
    """Convert color temperature to RGB."""
    temp = kelvin / 100
    if temp <= 66:
        r = 1.0
        g = max(0, min(1, (99.4708025861 * math.log(temp) - 161.1195681661) / 255))
    else:
        r = max(0, min(1, (329.698727446 * ((temp - 60) ** -0.1332047592)) / 255))
        g = max(0, min(1, (288.1221695283 * ((temp - 60) ** -0.0755148492)) / 255))
    b = (
        1.0
        if temp >= 66
        else (max(0, min(1, (138.5177312231 * math.log(temp - 10) - 305.0447927307) / 255)) if temp > 19 else 0)
    )
    return (r, g, b)


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
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
        params = {
            "room_type": "living_room",
            "width": 6,
            "length": 8,
            "height": 3,
            "style": "modern",
            "furniture": ["sofa", "table", "chandelier"],
            "camera_position": "corner",
        }

    output_path = args[1] if len(args) >= 2 else "output/interior.png"
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Clear
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    room_w = params.get("width", 6)
    room_l = params.get("length", 8)
    room_h = params.get("height", 3)
    style = params.get("style", "modern")

    # Build room
    objects, mats = build_room(room_w, room_l, room_h, style)

    # Add furniture
    furniture_list = params.get("furniture", ["sofa", "table", "chandelier"])
    for item in furniture_list:
        if item == "sofa":
            objects.extend(
                add_sofa((0, -room_l / 2 + 1, 0), color=mats["accent_color"] if "accent_color" in style else "#4a4a4a")
            )
        elif item == "table":
            objects.extend(add_table((0, 0, 0)))
        elif item == "bed":
            objects.extend(add_bed((0, 0, 0)))
        elif item == "chandelier":
            objects.extend(add_chandelier((0, 0, room_h - 0.3), style))

    # Setup lighting
    setup_interior_lighting(style, room_w, room_l, room_h)

    # Setup camera
    cam_pos = params.get("camera_position", "corner")
    if cam_pos == "corner":
        setup_interior_camera(
            (room_w / 2 - 0.5, -room_l / 2 + 0.5, room_h * 0.7), (0, 0, room_h * 0.4), focal_length=24
        )
    elif cam_pos == "center":
        setup_interior_camera((0, -room_l / 2 + 1, 1.6), (0, room_l / 4, 1.2), focal_length=35)

    # Render settings
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = params.get("samples", 256)
    scene.render.resolution_x = params.get("resolution", 1920)
    scene.render.resolution_y = params.get("resolution", 1080)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = output_path

    # World background (dark for interior)
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.02, 0.02, 0.05, 1.0)
        bg.inputs["Strength"].default_value = 0.1

    # Render
    bpy.ops.render.render(write_still=True)
    print(f"[ArchAI Interior] Rendered to {output_path}")


if __name__ == "__main__":
    main()
