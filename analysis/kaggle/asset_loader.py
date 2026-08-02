"""
Asset Loader для Blender — PBR текстуры, HDRI, GLB модели.

Используется внутри bpy-скриптов на Kaggle.
Загружает ассеты из Kaggle dataset и применяет к сцене.

Использование (в bpy скрипте):
    exec(open('/path/to/asset_loader.py').read())
    apply_pbr_material(wall_object, '/path/to/texture_dir')
    setup_hdri('/path/to/sky.hdr')
    import_furniture('/path/to/sofa.glb', location=(0, 0, 0))
"""

import bpy
import os
import json


# ============================================================
# PBR MATERIALS
# ============================================================

def load_image(path, colorspace="sRGB"):
    """Load image into Blender, set colorspace."""
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = colorspace
    return img


def apply_pbr_material(obj, texture_dir, name=None, uv_scale=1.0):
    """Apply PBR material from texture directory.
    
    texture_dir should contain:
      - albedo.jpg (or diffuse.jpg, basecolor.jpg)
      - roughness.jpg
      - normal.jpg (or nor_gl.jpg)
      - displacement.jpg (optional)
      - ao.jpg (optional)
    """
    if name is None:
        name = os.path.basename(texture_dir)
    
    # Find texture files (flexible naming)
    def find_file(names):
        for n in names:
            for ext in [".jpg", ".png", ".jpeg", ".tif", ".tiff"]:
                path = os.path.join(texture_dir, n + ext)
                if os.path.exists(path):
                    return path
        return None
    
    albedo_path = find_file(["albedo", "diffuse", "basecolor", "BaseColor", "Color"])
    rough_path = find_file(["roughness", "rough", "Roughness"])
    normal_path = find_file(["normal", "nor_gl", "Normal", "NormalGL"])
    disp_path = find_file(["displacement", "disp", "Displacement", "Height"])
    ao_path = find_file(["ao", "ambient_occlusion", "AO"])
    metallic_path = find_file(["metallic", "metal", "Metallic", "Metalness"])
    
    # Create material
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    
    # Clear default nodes
    for node in nodes:
        nodes.remove(node)
    
    # Principled BSDF
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    
    # Output
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (400, 0)
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    
    # Texture coordinate + mapping (for UV scale)
    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-800, 0)
    
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-600, 0)
    mapping.inputs["Scale"].default_value = (uv_scale, uv_scale, uv_scale)
    links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])
    
    # Albedo
    if albedo_path:
        tex_albedo = nodes.new("ShaderNodeTexImage")
        tex_albedo.location = (-400, 400)
        tex_albedo.image = load_image(albedo_path, "sRGB")
        links.new(mapping.outputs["Vector"], tex_albedo.inputs["Vector"])
        links.new(tex_albedo.outputs["Color"], bsdf.inputs["Base Color"])
    
    # Roughness
    if rough_path:
        tex_rough = nodes.new("ShaderNodeTexImage")
        tex_rough.location = (-400, 200)
        tex_rough.image = load_image(rough_path, "Non-Color")
        links.new(mapping.outputs["Vector"], tex_rough.inputs["Vector"])
        links.new(tex_rough.outputs["Color"], bsdf.inputs["Roughness"])
    
    # Normal Map
    if normal_path:
        tex_normal = nodes.new("ShaderNodeTexImage")
        tex_normal.location = (-400, -100)
        tex_normal.image = load_image(normal_path, "Non-Color")
        links.new(mapping.outputs["Vector"], tex_normal.inputs["Vector"])
        
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.location = (-100, -100)
        links.new(tex_normal.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    
    # Displacement
    if disp_path:
        tex_disp = nodes.new("ShaderNodeTexImage")
        tex_disp.location = (-400, -400)
        tex_disp.image = load_image(disp_path, "Non-Color")
        links.new(mapping.outputs["Vector"], tex_disp.inputs["Vector"])
        
        disp_node = nodes.new("ShaderNodeDisplacement")
        disp_node.location = (100, -400)
        disp_node.inputs["Scale"].default_value = 0.02
        links.new(tex_disp.outputs["Color"], disp_node.inputs["Height"])
        links.new(disp_node.outputs["Displacement"], output.inputs["Displacement"])
        
        mat.cycles.displacement_method = 'BOTH'
    
    # AO (multiply with albedo)
    if ao_path and albedo_path:
        tex_ao = nodes.new("ShaderNodeTexImage")
        tex_ao.location = (-400, 600)
        tex_ao.image = load_image(ao_path, "Non-Color")
        links.new(mapping.outputs["Vector"], tex_ao.inputs["Vector"])
        
        mix = nodes.new("ShaderNodeMixRGB")
        mix.location = (-100, 400)
        mix.blend_type = 'MULTIPLY'
        mix.inputs["Fac"].default_value = 1.0
        links.new(tex_albedo.outputs["Color"], mix.inputs["Color1"])
        links.new(tex_ao.outputs["Color"], mix.inputs["Color2"])
        links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    
    # Metallic
    if metallic_path:
        tex_metal = nodes.new("ShaderNodeTexImage")
        tex_metal.location = (-400, 0)
        tex_metal.image = load_image(metallic_path, "Non-Color")
        links.new(mapping.outputs["Vector"], tex_metal.inputs["Vector"])
        links.new(tex_metal.outputs["Color"], bsdf.inputs["Metallic"])
    
    # Apply to object
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    
    return mat


def create_simple_material(name, color, roughness=0.5, metallic=0.0):
    """Create a simple Principled BSDF material (no textures)."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        r, g, b = color[:3]
        bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


# ============================================================
# HDRI LIGHTING
# ============================================================

def setup_hdri(hdr_path, strength=1.0, rotation_z=0.0):
    """Setup HDRI environment lighting.
    
    Args:
        hdr_path: Path to .hdr or .exr file
        strength: Background light strength
        rotation_z: Rotation around Z axis (radians)
    """
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    
    # Clear existing
    nodes.clear()
    
    # Texture Coordinate
    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-600, 0)
    
    # Mapping (for rotation)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-400, 0)
    mapping.inputs["Rotation"].default_value = (0, 0, rotation_z)
    links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])
    
    # Environment Texture
    env = nodes.new("ShaderNodeTexEnvironment")
    env.location = (-200, 0)
    env.image = bpy.data.images.load(hdr_path)
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    
    # Background
    bg = nodes.new("ShaderNodeBackground")
    bg.location = (0, 0)
    bg.inputs["Strength"].default_value = strength
    links.new(env.outputs["Color"], bg.inputs["Color"])
    
    # Output
    output = nodes.new("ShaderNodeOutputWorld")
    output.location = (200, 0)
    links.new(bg.outputs["Background"], output.inputs["Surface"])
    
    print(f"  HDRI: {os.path.basename(hdr_path)}, strength={strength}")


# ============================================================
# GLB MODEL IMPORT
# ============================================================

def import_furniture(glb_path, location=(0, 0, 0), rotation=(0, 0, 0), scale=(1, 1, 1)):
    """Import GLB/GLTF model into scene.
    
    Args:
        glb_path: Path to .glb or .gltf file
        location: (x, y, z) position
        rotation: (rx, ry, rz) euler rotation in radians
        scale: (sx, sy, sz) scale factors
    
    Returns:
        List of imported objects
    """
    before = set(bpy.data.objects)
    
    try:
        bpy.ops.import_scene.gltf(filepath=glb_path)
    except Exception as e:
        print(f"  Error importing {glb_path}: {e}")
        return []
    
    after = set(bpy.data.objects)
    new_objects = list(after - before)
    
    if not new_objects:
        return []
    
    # Parent object (first new object or empty)
    parent = new_objects[0]
    
    # Create empty at location for grouping
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=location)
    empty = bpy.context.active_object
    empty.name = f"import_{os.path.basename(glb_path).split('.')[0]}"
    empty.rotation_euler = rotation
    empty.scale = scale
    
    # Parent imported objects to empty
    for obj in new_objects:
        obj.parent = empty
    
    return new_objects


def place_model(glb_path, location=(0, 0, 0), rotation=(0, 0, 0), scale=(1, 1, 1), name=None):
    """Import and place a GLB model."""
    objects = import_furniture(glb_path, location, rotation, scale)
    if objects and name:
        objects[0].name = name
    return objects


# ============================================================
# FURNITURE PLACEMENT HELPERS
# ============================================================

def furnish_living_room(models_dir, room_center=(0, 0, 0), room_size=(6, 5)):
    """Place furniture in a living room."""
    placed = []
    cx, cy, cz = room_center
    w, d = room_size
    
    # Sofa (against back wall)
    sofa_path = os.path.join(models_dir, "sofa.glb")
    if os.path.exists(sofa_path):
        placed += place_model(sofa_path, 
            location=(cx, cy + d/2 - 0.7, cz),
            rotation=(0, 0, 3.14159),
            name="Sofa")
    
    # Coffee table (center)
    table_path = os.path.join(models_dir, "table.glb")
    if os.path.exists(table_path):
        placed += place_model(table_path,
            location=(cx, cy, cz),
            name="CoffeeTable")
    
    # Bookshelf (side wall)
    shelf_path = os.path.join(models_dir, "shelf.glb")
    if os.path.exists(shelf_path):
        placed += place_model(shelf_path,
            location=(cx - w/2 + 0.3, cy, cz),
            rotation=(0, 0, 1.5708),
            name="Bookshelf")
    
    # Lamp (corner)
    lamp_path = os.path.join(models_dir, "lamp.glb")
    if os.path.exists(lamp_path):
        placed += place_model(lamp_path,
            location=(cx + w/2 - 0.5, cy - d/2 + 0.5, cz),
            name="FloorLamp")
    
    # Plant
    plant_path = os.path.join(models_dir, "plant.glb")
    if os.path.exists(plant_path):
        placed += place_model(plant_path,
            location=(cx + w/2 - 0.5, cy + d/2 - 0.5, cz),
            name="Plant")
    
    print(f"  Living room: {len(placed)} objects placed")
    return placed


def furnish_bedroom(models_dir, room_center=(0, 0, 0), room_size=(5, 4)):
    """Place furniture in a bedroom."""
    placed = []
    cx, cy, cz = room_center
    w, d = room_size
    
    # Bed (center)
    bed_path = os.path.join(models_dir, "bed.glb")
    if os.path.exists(bed_path):
        placed += place_model(bed_path,
            location=(cx, cy, cz),
            name="Bed")
    
    # Nightstand
    table_path = os.path.join(models_dir, "table.glb")
    if os.path.exists(table_path):
        placed += place_model(table_path,
            location=(cx - 1.2, cy, cz),
            scale=(0.5, 0.5, 0.5),
            name="Nightstand")
    
    # Lamp
    lamp_path = os.path.join(models_dir, "lamp.glb")
    if os.path.exists(lamp_path):
        placed += place_model(lamp_path,
            location=(cx - 1.2, cy + 0.3, cz + 0.5),
            scale=(0.3, 0.3, 0.3),
            name="BedsideLamp")
    
    print(f"  Bedroom: {len(placed)} objects placed")
    return placed


def furnish_kitchen(models_dir, room_center=(0, 0, 0), room_size=(5, 4)):
    """Place furniture in a kitchen."""
    placed = []
    cx, cy, cz = room_center
    w, d = room_size
    
    # Table (dining)
    table_path = os.path.join(models_dir, "table.glb")
    if os.path.exists(table_path):
        placed += place_model(table_path,
            location=(cx, cy, cz),
            name="DiningTable")
    
    # Chairs (4 around table)
    chair_path = os.path.join(models_dir, "chair.glb")
    if os.path.exists(chair_path):
        for i, (dx, dy) in enumerate([(-0.8, 0), (0.8, 0), (0, -0.8), (0, 0.8)]):
            rot = (0, 0, [0, 3.14, 1.57, -1.57][i])
            placed += place_model(chair_path,
                location=(cx + dx, cy + dy, cz),
                rotation=rot,
                scale=(0.8, 0.8, 0.8),
                name=f"Chair_{i}")
    
    print(f"  Kitchen: {len(placed)} objects placed")
    return placed


# ============================================================
# MANIFEST LOADER
# ============================================================

def load_manifest(manifest_path):
    """Load asset manifest and return dict."""
    with open(manifest_path) as f:
        return json.load(f)


def get_texture_dir(manifest, category):
    """Get texture directory for a category (e.g., 'brick', 'wood')."""
    textures = manifest.get("textures", {})
    
    # Direct match
    for name, maps in textures.items():
        if category.lower() in name.lower():
            return os.path.dirname(list(maps.values())[0])
    
    # Partial match
    for name, maps in textures.items():
        if any(c in name.lower() for c in [category.lower()[:4]]):
            return os.path.dirname(list(maps.values())[0])
    
    return None


def get_hdri(manifest, preference="sky"):
    """Get HDRI path, preferring certain types."""
    hdris = manifest.get("hdris", [])
    if not hdris:
        return None
    
    # Preference match
    for path in hdris:
        if preference.lower() in os.path.basename(path).lower():
            return path
    
    # Default: first
    return hdris[0]


def get_model(manifest, category):
    """Get model path for a category (e.g., 'sofa', 'table', 'chair')."""
    models = manifest.get("models", {})
    
    for name, path in models.items():
        if category.lower() in name.lower():
            return path
    
    return None
