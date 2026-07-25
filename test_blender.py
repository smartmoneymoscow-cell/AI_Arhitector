import bpy
import os
import sys

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Create a simple cube
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
cube = bpy.context.active_object
cube.name = "TestCube"

# Camera
cam = bpy.data.cameras.new("Cam")
cam_obj = bpy.data.objects.new("Cam", cam)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj
cam_obj.location = (5, -5, 5)
cam_obj.rotation_euler = (1.1, 0, 0.8)

# Light
light = bpy.data.lights.new("Light", "POINT")
light.energy = 500
light_obj = bpy.data.objects.new("Light", light)
bpy.context.collection.objects.link(light_obj)
light_obj.location = (3, -3, 5)

# Render settings
output_path = "/app/output/test_render.png"
bpy.context.scene.render.filepath = output_path
bpy.context.scene.render.engine = 'BLENDER_EEVEE'
bpy.context.scene.render.resolution_x = 640
bpy.context.scene.render.resolution_y = 480

print(f"Rendering to {output_path}...")
try:
    bpy.ops.render.render(write_still=True)
    if os.path.exists(output_path):
        print(f"SUCCESS: {os.path.getsize(output_path)} bytes")
    else:
        print("FAIL: output file not created")
except Exception as e:
    print(f"RENDER ERROR: {e}")

# Also try GLB export
glb_path = "/app/output/test_export.glb"
try:
    bpy.ops.export_scene.gltf(filepath=glb_path, export_format='GLB')
    if os.path.exists(glb_path):
        print(f"GLB SUCCESS: {os.path.getsize(glb_path)} bytes")
    else:
        print("GLB FAIL")
except Exception as e:
    print(f"GLB ERROR: {e}")
