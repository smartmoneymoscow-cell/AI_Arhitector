"""
Architect — Monolith Server (FastAPI)
Serves frontend + proxies LLM API + generates Blender scripts.

Use for LOCAL DEVELOPMENT. For production, use docker-compose with microservices.

Endpoints:
    GET  /                           — Web interface
    GET  /health                     — Health check
    POST /api/v1/generate            — Unified: text → GLB/PNG (with routing)
    POST /api/v1/generate/building   — Text → GLB (legacy)
    POST /api/v1/render/interior     — Interior → PNG (legacy)
    POST /api/v1/proxy/claude        — Chat proxy
    GET  /docs                       — OpenAPI documentation
"""

import os
import uuid
import subprocess

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from promt_parser import (
    fallback_regex_parse,
    parse_prompt_sync,
    get_generation_type,
    DEFAULT_FURNITURE,
)

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
FREE_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"
PORT = int(os.environ.get("PORT", 8080))
FRONTEND_DIR = os.path.dirname(__file__)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
BLENDER = os.environ.get("BLENDER_PATH", "blender")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════
app = FastAPI(
    title="Architect Server",
    description="Монолитный сервер для локальной разработки",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════
class GenerateRequest(BaseModel):
    prompt: str
    object_type: str | None = None
    building_type: str = "house"
    room_type: str | None = None
    floors: int = 2
    width_m: int = 10
    length_m: int = 12
    height_m: int = 3
    style: str = "modern"
    material: str = "plaster"
    roof_type: str = "gabled"
    features: list = []
    furniture: list = []


# ═══════════════════════════════════════════════════════════════
# BPY SCRIPT GENERATORS (imported from blender-service logic)
# ═══════════════════════════════════════════════════════════════
def safe_val(value, default, valid_values=None):
    if value is None:
        return default
    if valid_values is not None and value not in valid_values:
        return default
    return value


def generate_bpy_script(params):
    W = safe_val(params.get("width"), 10, range(1, 201))
    L = safe_val(params.get("length"), 12, range(1, 201))
    floors = safe_val(params.get("floors"), 2, range(1, 21))
    fH = safe_val(params.get("floor_height"), 3.0)
    thick = safe_val(params.get("wall_thickness"), 0.3)
    roof_type = safe_val(params.get("roof_type"), "gabled", ["gabled", "flat", "hip"])
    mat = safe_val(
        params.get("facade_material"), "plaster",
        ["brick", "wood", "glass", "stone", "concrete", "plaster"],
    )
    has_balcony = bool(params.get("has_balcony", False))
    has_terrace = bool(params.get("has_terrace", False))
    has_garage = bool(params.get("has_garage", False))

    colors = {
        "brick": (0.71, 0.40, 0.12), "wood": (0.55, 0.41, 0.13),
        "glass": (0.53, 0.81, 0.92), "plaster": (0.91, 0.88, 0.83),
        "stone": (0.50, 0.50, 0.50), "concrete": (0.63, 0.63, 0.63),
    }
    wr, wg, wb = colors.get(mat, (0.91, 0.88, 0.83))
    total_h = floors * fH

    script = f"""import bpy, os, math
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
W={W};L={L};floors={floors};fH={fH};thick={thick};total_h=floors*fH
def make_mat(n,c,r=0.8,m=0.0):
    mat=bpy.data.materials.new(n);mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:bsdf.inputs["Base Color"].default_value=(*c,1.0);bsdf.inputs["Roughness"].default_value=r;bsdf.inputs["Metallic"].default_value=m
    return mat
wall_mat=make_mat("Wall",({wr},{wg},{wb}));roof_mat=make_mat("Roof",(0.545,0.271,0.075))
glass_mat=make_mat("Glass",(0.8,0.9,1.0),0.05,0.1);ground_mat=make_mat("Grass",(0.29,0.49,0.25))
concrete_mat=make_mat("Concrete",(0.5,0.5,0.5),0.95);door_mat=make_mat("Door",(0.29,0.22,0.16))
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,-0.15))
fnd=bpy.context.active_object;fnd.name="Foundation";fnd.scale=(W/2+0.3,L/2+0.3,0.15)
bpy.ops.object.transform_apply(scale=True);fnd.data.materials.append(concrete_mat)
for floor in range(floors):
    z=floor*fH+fH/2
    for side,(sx,sy) in [("F",(0,-L/2)),("B",(0,L/2)),("L",(-W/2,0)),("R",(W/2,0))]:
        is_x=side in ("L","R")
        bpy.ops.mesh.primitive_cube_add(size=1,location=(sx,sy,z))
        w=bpy.context.active_object;w.name=f"Wall_{{side}}_{{floor}}"
        w.scale=((thick if is_x else W)/2,(L if is_x else thick)/2,fH/2)
        bpy.ops.object.transform_apply(scale=True);w.data.materials.append(wall_mat)
    n_win=max(2,W//3)
    for i in range(n_win):
        x=-W/2+(i+1)*W/(n_win+1)
        bpy.ops.mesh.primitive_plane_add(size=1,location=(x,-L/2-thick/2-0.01,floor*fH+fH*0.4))
        g=bpy.context.active_object;g.name=f"Window_{{floor}}_{{i}}";g.scale=(1.2,0.02,1.5);g.data.materials.append(glass_mat)
    if floor>0:
        bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,floor*fH))
        slab=bpy.context.active_object;slab.name=f"Slab_{{floor}}";slab.scale=(W/2,L/2,0.1)
        bpy.ops.object.transform_apply(scale=True);slab.data.materials.append(concrete_mat)
rh=2.5
if "{roof_type}"=="gabled":
    verts=[(-W/2-0.3,-L/2-0.3,total_h),(W/2+0.3,-L/2-0.3,total_h),(W/2+0.3,L/2+0.3,total_h),(-W/2-0.3,L/2+0.3,total_h),(0,-L/2-0.3,total_h+rh),(0,L/2+0.3,total_h+rh)]
    faces=[(0,1,4),(2,3,5),(0,3,5,4),(1,2,5,4)]
    mesh=bpy.data.meshes.new("RoofMesh");mesh.from_pydata(verts,[],faces);mesh.update()
    roof=bpy.data.objects.new("Roof",mesh);bpy.context.collection.objects.link(roof);roof.data.materials.append(roof_mat)
elif "{roof_type}"=="flat":
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,total_h+0.1))
    roof=bpy.context.active_object;roof.name="Roof";roof.scale=(W/2+0.3,L/2+0.3,0.1)
    bpy.ops.object.transform_apply(scale=True);roof.data.materials.append(roof_mat)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2-thick/2-0.01,1.1))
door=bpy.context.active_object;door.name="Door";door.scale=(0.5,0.04,1.1);door.data.materials.append(door_mat)
bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.data.objects:
    if obj.name not in ('Ground','Camera','Sun') and obj.type=='MESH':
        obj.select_set(True)
bpy.context.view_layer.objects.active=bpy.data.objects.get('Foundation')
bpy.ops.object.join()
bpy.context.active_object.name='Building'
"""
    if has_balcony:
        script += """
for floor in range(1,floors):
    z=floor*fH
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2-1.5,z+0.05))
    balc=bpy.context.active_object;balc.name=f"Balcony_{floor}";balc.scale=(1.5,0.75,0.05)
    bpy.ops.object.transform_apply(scale=True);balc.data.materials.append(concrete_mat)
    bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2-2.2,z+0.6))
    rail=bpy.context.active_object;rail.name=f"Railing_{floor}";rail.scale=(1.5,0.03,0.5);rail.data.materials.append(wall_mat)
"""
    script += f"""
bpy.ops.mesh.primitive_plane_add(size=50,location=(0,0,-0.01))
gnd=bpy.context.active_object;gnd.name="Ground";gnd.data.materials.append(ground_mat)
cam=bpy.data.cameras.new("Camera");cam_obj=bpy.data.objects.new("Camera",cam)
bpy.context.scene.collection.objects.link(cam_obj);bpy.context.scene.camera=cam_obj
cam_obj.location=(W*1.5,-L*1.5,total_h*1.2);cam_obj.rotation_euler=(math.radians(60),0,math.radians(45))
sun=bpy.data.lights.new("Sun","SUN");sun.energy=3
sun_obj=bpy.data.objects.new("Sun",sun);bpy.context.collection.objects.link(sun_obj)
sun_obj.rotation_euler=(math.radians(45),math.radians(15),math.radians(30))
world=bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world=world;world.use_nodes=True
bg=world.node_tree.nodes.get("Background")
if bg:bg.inputs["Color"].default_value=(0.5,0.7,1.0,1.0);bg.inputs["Strength"].default_value=1.0
"""
    if has_terrace:
        script += """
bpy.ops.mesh.primitive_cube_add(size=1,location=(W/2+2,0,0.05))
terr=bpy.context.active_object;terr.name="Terrace";terr.scale=(1.5,L/2,0.05)
bpy.ops.object.transform_apply(scale=True);terr.data.materials.append(concrete_mat)
"""
    if has_garage:
        script += """
bpy.ops.mesh.primitive_cube_add(size=1,location=(-W/2-3,0,1.5))
garage=bpy.context.active_object;garage.name="Garage";garage.scale=(2,2.5,1.5)
bpy.ops.object.transform_apply(scale=True);garage.data.materials.append(wall_mat)
bpy.ops.mesh.primitive_cube_add(size=1,location=(-W/2-3,-2.5,1.2))
gd=bpy.context.active_object;gd.name="GarageDoor";gd.scale=(1.75,0.04,1.2);gd.data.materials.append(door_mat)
"""
    return script


def generate_interior_script(params):
    w = params.get("width", 6)
    l = params.get("length", 8)
    h = params.get("height", 3)
    style = params.get("style", "modern")
    furniture = params.get("furniture", ["sofa", "table", "chandelier"])

    style_colors = {
        "modern": {"wall": (0.96, 0.96, 0.96), "floor": (0.77, 0.66, 0.51), "accent": (0.17, 0.24, 0.31)},
        "classic": {"wall": (0.94, 0.90, 0.83), "floor": (0.55, 0.41, 0.08), "accent": (0.55, 0.0, 0.0)},
        "scandinavian": {"wall": (0.98, 0.98, 0.98), "floor": (0.83, 0.72, 0.59), "accent": (0.56, 0.74, 0.56)},
        "loft": {"wall": (0.63, 0.63, 0.63), "floor": (0.42, 0.42, 0.42), "accent": (1.0, 0.42, 0.21)},
        "minimalist": {"wall": (1.0, 1.0, 1.0), "floor": (0.88, 0.85, 0.80), "accent": (0.0, 0.0, 0.0)},
        "hitech": {"wall": (0.9, 0.9, 0.95), "floor": (0.3, 0.3, 0.35), "accent": (0.0, 0.6, 0.8)},
    }
    sc = style_colors.get(style, style_colors["modern"])

    script = f"""import bpy, math
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
W={w};L={l};H={h}
def make_mat(n,c,r=0.8,e=0.0):
    mat=bpy.data.materials.new(n);mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value=(*c,1.0);bsdf.inputs["Roughness"].default_value=r
        if e>0:
            try:bsdf.inputs["Emission Color"].default_value=(*c,1.0)
            except:bsdf.inputs["Emission"].default_value=(*c,1.0)
            try:bsdf.inputs["Emission Strength"].default_value=e
            except:pass
    return mat
wall_mat=make_mat("Wall",{sc['wall']},0.9)
floor_mat=make_mat("Floor",{sc['floor']},0.6)
ceiling_mat=make_mat("Ceiling",(1,1,1),0.95)
bpy.ops.mesh.primitive_plane_add(size=1,location=(0,0,0))
fl=bpy.context.active_object;fl.name="Floor";fl.scale=(W/2,L/2,1)
bpy.ops.object.transform_apply(scale=True);fl.data.materials.append(floor_mat)
bpy.ops.mesh.primitive_plane_add(size=1,location=(0,0,H))
ceil=bpy.context.active_object;ceil.name="Ceiling";ceil.scale=(W/2,L/2,1)
ceil.rotation_euler.x=math.pi
bpy.ops.object.transform_apply(scale=True,rotation=True);ceil.data.materials.append(ceiling_mat)
for name,(sx,sy),(dx,dy) in [("Front",(0,-L/2),(W,0.15)),("Back",(0,L/2),(W,0.15)),("Left",(-W/2,0),(0.15,L)),("Right",(W/2,0),(0.15,L))]:
    bpy.ops.mesh.primitive_cube_add(size=1,location=(sx,sy,H/2))
    wall=bpy.context.active_object;wall.name=name;wall.scale=(dx/2,dy/2,H/2)
    bpy.ops.object.transform_apply(scale=True);wall.data.materials.append(wall_mat)
"""
    furniture_scripts = {
        "sofa": """
sofa_mat=make_mat("Sofa",(0.29,0.29,0.29),0.85)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2+1,0.3))
seat=bpy.context.active_object;seat.name="Sofa_Seat";seat.scale=(1,0.5,0.3)
bpy.ops.object.transform_apply(scale=True);seat.data.materials.append(sofa_mat)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-L/2+1.35,0.65))
back=bpy.context.active_object;back.name="Sofa_Back";back.scale=(1,0.1,0.35)
bpy.ops.object.transform_apply(scale=True);back.data.materials.append(sofa_mat)
""",
        "table": """
table_mat=make_mat("Table",(0.55,0.41,0.08),0.6)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,0.75))
top=bpy.context.active_object;top.name="Table_Top";top.scale=(0.6,0.4,0.04)
bpy.ops.object.transform_apply(scale=True);top.data.materials.append(table_mat)
for dx,dy in [(-1,-1),(1,-1),(-1,1),(1,1)]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.03,depth=0.75,location=(dx*0.5,dy*0.3,0.375))
    leg=bpy.context.active_object;leg.name="Table_Leg";leg.data.materials.append(table_mat)
""",
        "bed": """
bed_mat=make_mat("Bed",(0.94,0.94,0.94),0.9)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0,0.25))
mattress=bpy.context.active_object;mattress.name="Mattress";mattress.scale=(0.9,1,0.25)
bpy.ops.object.transform_apply(scale=True);mattress.data.materials.append(bed_mat)
bpy.ops.mesh.primitive_cube_add(size=1,location=(0,0.95,0.6))
hb=bpy.context.active_object;hb.name="Headboard";hb.scale=(0.9,0.05,0.6)
hb.data.materials.append(make_mat("Headboard",(0.24,0.17,0.12),0.7))
""",
        "chandelier": """
bpy.ops.mesh.primitive_cylinder_add(radius=0.01,depth=1,location=(0,0,H-0.5))
wire=bpy.context.active_object;wire.name="Wire"
wire.data.materials.append(make_mat("Metal",(0.2,0.2,0.2),0.3,0.8))
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2,location=(0,0,H-1))
shade=bpy.context.active_object;shade.name="Shade"
shade.data.materials.append(make_mat("Light",(1,0.96,0.88),0.5,5.0))
light_data=bpy.data.lights.new("Chandelier","POINT");light_data.energy=500;light_data.color=(1.0,0.95,0.85)
light_obj=bpy.data.objects.new("Chandelier",light_data)
bpy.context.collection.objects.link(light_obj);light_obj.location=(0,0,H-1)
""",
    }
    for item in furniture:
        if item in furniture_scripts:
            script += furniture_scripts[item]

    script += """
cam=bpy.data.cameras.new("InteriorCam");cam.lens=24
cam_obj=bpy.data.objects.new("Camera",cam)
bpy.context.scene.collection.objects.link(cam_obj);bpy.context.scene.camera=cam_obj
cam_obj.location=(W/2-0.5,-L/2+0.5,H*0.7)
cam_obj.rotation_euler=(math.radians(60),0,math.radians(45))
sun=bpy.data.lights.new("Sun","SUN");sun.energy=3
sun_obj=bpy.data.objects.new("Sun",sun)
bpy.context.collection.objects.link(sun_obj)
sun_obj.rotation_euler=(math.radians(50),math.radians(20),math.radians(-30))
world=bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world=world;world.use_nodes=True
bg=world.node_tree.nodes.get("Background")
if bg:bg.inputs["Color"].default_value=(0.02,0.02,0.05,1.0);bg.inputs["Strength"].default_value=0.1
"""
    return script


# ═══════════════════════════════════════════════════════════════
# BLENDER EXECUTION
# ═══════════════════════════════════════════════════════════════
def run_blender(script: str, output_file: str, timeout: int = 120) -> subprocess.CompletedProcess:
    job_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(OUTPUT_DIR, f"{job_id}.py")

    try:
        compile(script, f"<{job_id}>", "exec")
    except SyntaxError as e:
        raise HTTPException(500, f"Script syntax error: {e}")

    with open(script_path, "w") as f:
        f.write(script)

    try:
        result = subprocess.run(
            [BLENDER, "--background", "--factory-startup", "--log-level", "0", "--python", script_path],
            capture_output=True, text=True, timeout=timeout,
        )
        return result
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"Blender timeout ({timeout}s)")
    except Exception as e:
        raise HTTPException(500, f"Blender failed: {e}")
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════
@app.get("/health")
@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "archai-server", "model": FREE_MODEL, "free": True}


@app.post("/api/v1/generate")
async def generate(req: GenerateRequest):
    """Единый endpoint: промт → парсинг (LLM + fallback) → роутинг → генерация."""
    # Парсинг: LLM с fallback на regex
    try:
        params = parse_prompt_sync(req.prompt, OPENROUTER_KEY)
    except Exception:
        params = fallback_regex_parse(req.prompt)

    gen_type = get_generation_type(params)

    if gen_type == "interior":
        room_type = params.get("room_type", "living")
        furniture = params.get("furniture") or DEFAULT_FURNITURE.get(room_type, ["sofa", "table", "chandelier"])
        interior_params = {
            "width": params.get("width_m", 6),
            "length": params.get("length_m", 8),
            "height": params.get("height_m", 3),
            "style": params.get("style", "modern"),
            "furniture": furniture,
        }
        script = generate_interior_script(interior_params)
        job_id = uuid.uuid4().hex[:8]
        output_file = os.path.join(OUTPUT_DIR, f"{job_id}_int.png")

        render_cmd = (
            "\nimport bpy"
            f"\nbpy.context.scene.render.filepath = r'{output_file}'"
            "\nbpy.context.scene.render.engine = 'BLENDER_EEVEE'"
            "\nbpy.context.scene.render.resolution_x = 640"
            "\nbpy.context.scene.render.resolution_y = 480"
            "\nbpy.ops.render.render(write_still=True)"
        )
        run_blender(script + render_cmd, output_file, timeout=300)

        if os.path.exists(output_file):
            return FileResponse(output_file, media_type="image/png",
                               filename=f"archai_interior_{job_id}.png")
        raise HTTPException(500, "Render failed")
    else:
        building_params = {
            "width": params.get("width_m", 10),
            "length": params.get("length_m", 12),
            "floors": params.get("floors", 2),
            "roof_type": params.get("roof_type", "gabled"),
            "facade_material": params.get("material", "plaster"),
            "has_balcony": "balcony" in params.get("features", []),
            "has_terrace": "terrace" in params.get("features", []),
            "has_garage": "garage" in params.get("features", []),
        }
        script = generate_bpy_script(building_params)
        job_id = uuid.uuid4().hex[:8]
        output_file = os.path.join(OUTPUT_DIR, f"{job_id}.glb")

        export_cmd = f"\nimport bpy\nbpy.ops.export_scene.gltf(filepath=r'{output_file}', export_format='GLB')"
        result = run_blender(script + export_cmd, output_file, timeout=120)

        if os.path.exists(output_file):
            return FileResponse(output_file, media_type="model/gltf-binary",
                               filename=f"archai_{job_id}.glb")
        raise HTTPException(500, detail={"error": "Export failed", "stderr": (result.stderr or "")[-500:]})


@app.post("/api/v1/generate/building")
async def generate_building_legacy(req: GenerateRequest):
    req.object_type = "building"
    return await generate(req)


@app.post("/api/v1/render/interior")
async def render_interior_legacy(req: GenerateRequest):
    req.object_type = "interior"
    return await generate(req)


@app.post("/api/v1/proxy/claude")
async def proxy_claude(request: Request):
    data = await request.json()
    headers = {"Content-Type": "application/json", "HTTP-Referer": "https://archai.app", "X-Title": "Architect"}
    if OPENROUTER_KEY:
        headers["Authorization"] = f"Bearer {OPENROUTER_KEY}"

    messages = data.get("messages", [])
    system = data.get("system", "Отвечай по-русски.")
    openai_msgs = [{"role": "system", "content": system}]
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            parts = []
            for b in content:
                if b.get("type") == "text":
                    parts.append({"type": "text", "text": b.get("text", "")})
                elif b.get("type") == "image":
                    src = b.get("source", {})
                    if src.get("type") == "base64":
                        parts.append({"type": "image_url", "image_url": {"url": f"data:{src.get('media_type', 'image/jpeg')};base64,{src.get('data', '')}"}})
            openai_msgs.append({"role": role, "content": parts if parts else str(content)})
        else:
            openai_msgs.append({"role": role, "content": str(content)})

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers=headers,
                json={"model": FREE_MODEL, "messages": openai_msgs, "max_tokens": data.get("max_tokens", 400), "temperature": 0.7},
                timeout=60.0,
            )
        if r.status_code == 200:
            text = r.json()["choices"][0]["message"]["content"]
            return {"content": [{"type": "text", "text": text or ""}]}
        raise HTTPException(r.status_code, detail=r.text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, str(e))


# ═══════════════════════════════════════════════════════════════
# STATIC FILES
# ═══════════════════════════════════════════════════════════════
@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/{filename:path}")
async def serve_static(filename: str):
    path = os.path.join(FRONTEND_DIR, filename)
    if os.path.isfile(path):
        return FileResponse(path)
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    print(f"🏗️  Architect Server starting on port {PORT}")
    print(f"📡 OpenRouter: {FREE_MODEL} (free)")
    print(f"🌐 http://localhost:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
