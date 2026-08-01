"""
ArchAI ↔ BlenderLLM Bridge
Converts natural language prompts into Blender bpy scripts via BlenderLLM model.
Falls back to Claude API if model is unavailable.

Based on: https://github.com/FreedomIntelligence/BlenderLLM
Model: FreedomIntelligence/BlenderLLM (Qwen2.5-Coder-7B-Instruct fine-tuned)

Usage:
    from blenderllm_bridge import BlenderLLMBridge
    bridge = BlenderLLMBridge(model_path="FreedomIntelligence/BlenderLLM")
    bpy_script = bridge.generate("двухэтажный кирпичный дом 10x12")
    bridge.run_in_blender(bpy_script, "output/building.glb")
"""

import json
import logging
import os
import re
import subprocess
import tempfile

logger = logging.getLogger("archai.blenderllm")

# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT (from BlenderLLM)
# ═══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are an expert in using bpy script to create 3D models. Based on the following instruction, your task is to write the corresponding bpy script that will generate the desired 3D model in Blender. Please pay close attention to every detail in the script and ensure it fully adheres to the provided specifications.

Important rules:
1. Start with: import bpy, import os, import math
2. Clear scene first: bpy.ops.object.select_all(action='SELECT') then bpy.ops.object.delete()
3. Use proper bpy API calls for geometry
4. Apply materials with Principled BSDF nodes
5. Set up camera and lighting
6. The script must be complete and runnable
7. Do NOT include any markdown formatting, just raw Python code"""

# ═══════════════════════════════════════════════════════════════
# CLAUDE FALLBACK PROMPT
# ═══════════════════════════════════════════════════════════════
CLAUDE_SYSTEM = """You are an expert Blender Python (bpy) scripter. Generate ONLY valid, runnable bpy Python code.

Rules:
- Start with: import bpy, import os, import math
- Clear scene: bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
- Use proper geometry primitives (cube, cylinder, sphere, mesh)
- Apply materials via Principled BSDF
- Include camera + light setup
- No markdown, no explanations — ONLY raw Python code
- Code must run in Blender 4.0+ headless mode"""


class BlenderLLMBridge:
    """Bridge between user prompts and Blender 3D generation."""

    def __init__(
        self,
        model_path="FreedomIntelligence/BlenderLLM",
        blender_path="blender",
        anthropic_key=None,
        anthropic_base=None,
    ):
        self.model_path = model_path
        self.blender_path = blender_path
        self.anthropic_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.anthropic_base = anthropic_base or os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        self._model = None
        self._tokenizer = None
        self._model_loaded = False

    # ── Model Loading ──────────────────────────────────────────
    def load_model(self):
        """Load BlenderLLM model (requires GPU, ~14GB VRAM)."""
        if self._model_loaded:
            return True
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            logger.info(f"Loading BlenderLLM model: {self.model_path}")
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16,
                device_map="auto",
                trust_remote_code=True,
            )
            self._model_loaded = True
            logger.info("BlenderLLM model loaded successfully")
            return True
        except Exception as e:
            logger.warning(f"Failed to load BlenderLLM model: {e}")
            return False

    # ── Script Generation ──────────────────────────────────────
    def generate(self, prompt, max_tokens=2048):
        """Generate bpy script from natural language prompt.

        Tries BlenderLLM first, falls back to Claude API.
        Returns: str (bpy Python script)
        """
        # Try BlenderLLM model
        if self._model_loaded or self.load_model():
            try:
                return self._generate_with_model(prompt, max_tokens)
            except Exception as e:
                logger.warning(f"BlenderLLM inference failed: {e}, falling back to Claude")

        # Fallback: Claude API
        if self.anthropic_key:
            try:
                return self._generate_with_claude(prompt, max_tokens)
            except Exception as e:
                logger.error(f"Claude fallback failed: {e}")

        # Last resort: template-based generation
        logger.warning("No model available, using template generation")
        return self._generate_template(prompt)

    def _generate_with_model(self, prompt, max_tokens=2048):
        """Generate using BlenderLLM (Qwen2.5-Coder-7B fine-tuned)."""
        import torch

        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
        text = self._tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self._tokenizer([text], return_tensors="pt").to(self._model.device)

        with torch.no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
            )

        generated = output_ids[0][len(inputs.input_ids[0]) :]
        response = self._tokenizer.decode(generated, skip_special_tokens=True)
        return self._clean_script(response)

    def _generate_with_claude(self, prompt, max_tokens=2048):
        """Generate using Claude API as fallback."""
        import httpx

        messages = [{"role": "user", "content": f"Generate a complete bpy script for: {prompt}"}]

        r = httpx.post(
            f"{self.anthropic_base}/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.anthropic_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": max_tokens,
                "system": CLAUDE_SYSTEM,
                "messages": messages,
            },
            timeout=60.0,
        )
        r.raise_for_status()
        response = r.json()["content"][0]["text"]
        return self._clean_script(response)

    def _generate_template(self, prompt):
        """Template-based fallback when no model is available."""
        p = prompt.lower()
        params = self._parse_params(p)

        return f'''import bpy
import os
import math

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Parameters from prompt: {prompt}
W = {params["width"]}
L = {params["length"]}
floors = {params["floors"]}
fH = 3.0
thick = 0.3

# Materials
def make_mat(name, color, rough=0.8):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
    return mat

wall_mat = make_mat("Wall", ({params["wall_r"]}, {params["wall_g"]}, {params["wall_b"]}))
roof_mat = make_mat("Roof", (0.545, 0.271, 0.075))
glass_mat = make_mat("Glass", (0.8, 0.9, 1.0), 0.05)
ground_mat = make_mat("Grass", (0.29, 0.49, 0.25))

# Foundation
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.15))
fnd = bpy.context.active_object
fnd.name = "Foundation"
fnd.scale = (W+0.6, L+0.6, 0.3)
bpy.ops.object.transform_apply(scale=True)
fnd.data.materials.append(make_mat("Concrete", (0.5, 0.5, 0.5)))

# Walls
total_h = floors * fH
for floor in range(floors):
    z = floor * fH + fH/2
    for name, loc, scl in [
        ("Wall_F", (0, -L/2, z), (W, thick, fH)),
        ("Wall_B", (0, L/2, z), (W, thick, fH)),
        ("Wall_L", (-W/2, 0, z), (thick, L, fH)),
        ("Wall_R", (W/2, 0, z), (thick, L, fH)),
    ]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
        w = bpy.context.active_object
        w.name = f"{{name}}_{{floor}}"
        w.scale = (scl[0]/2, scl[1]/2, scl[2]/2)
        bpy.ops.object.transform_apply(scale=True)
        w.data.materials.append(wall_mat)

    # Windows
    n_win = 3
    for i in range(n_win):
        x = -W/2 + (i+1)*W/(n_win+1)
        bpy.ops.mesh.primitive_plane_add(size=1, location=(x, -L/2-thick/2, floor*fH+fH*0.4))
        g = bpy.context.active_object
        g.name = f"Window_{{floor}}_{{i}}"
        g.scale = (1.2, 0.02, 1.5)
        g.data.materials.append(glass_mat)

# Floor slabs
for floor in range(1, floors):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, floor*fH))
    slab = bpy.context.active_object
    slab.name = f"Slab_{{floor}}"
    slab.scale = (W/2, L/2, 0.1)
    bpy.ops.object.transform_apply(scale=True)
    slab.data.materials.append(wall_mat)

# Roof
rh = {params["roof_h"]}
if "{params["roof_type"]}" == "gabled":
    verts = [
        (-W/2-0.3, -L/2-0.3, total_h), (W/2+0.3, -L/2-0.3, total_h),
        (W/2+0.3, L/2+0.3, total_h), (-W/2-0.3, L/2+0.3, total_h),
        (0, -L/2-0.3, total_h+rh), (0, L/2+0.3, total_h+rh),
    ]
    faces = [(0,1,4), (2,3,5), (0,3,5,4), (1,2,5,4)]
    mesh = bpy.data.meshes.new("RoofMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    roof = bpy.data.objects.new("Roof", mesh)
    bpy.context.collection.objects.link(roof)
    roof.data.materials.append(roof_mat)
elif "{params["roof_type"]}" == "flat":
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, total_h+0.1))
    roof = bpy.context.active_object
    roof.name = "Roof"
    roof.scale = (W/2+0.3, L/2+0.3, 0.1)
    bpy.ops.object.transform_apply(scale=True)
    roof.data.materials.append(roof_mat)

# Door
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -L/2-thick/2, 1.1))
door = bpy.context.active_object
door.name = "Door"
door.scale = (0.5, 0.04, 1.1)
door.data.materials.append(make_mat("Door", (0.29, 0.22, 0.16)))

# Ground
bpy.ops.mesh.primitive_plane_add(size=50, location=(0, 0, -0.01))
gnd = bpy.context.active_object
gnd.name = "Ground"
gnd.data.materials.append(ground_mat)

# Camera
cam = bpy.data.cameras.new("Camera")
cam_obj = bpy.data.objects.new("Camera", cam)
bpy.context.scene.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj
cam_obj.location = (W*1.5, -L*1.5, total_h*1.2)
cam_obj.rotation_euler = (math.radians(60), 0, math.radians(45))

# Sun
sun = bpy.data.lights.new("Sun", "SUN")
sun.energy = 3
sun_obj = bpy.data.objects.new("Sun", sun)
bpy.context.collection.objects.link(sun_obj)
sun_obj.rotation_euler = (math.radians(45), math.radians(15), math.radians(30))

# World
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value = (0.5, 0.7, 1.0, 1.0)
'''

    # ── Blender Execution ──────────────────────────────────────
    def run_in_blender(self, bpy_script, output_path, export_format="glb", render_preview=False, preview_path=None):
        """Execute bpy script in Blender and export result.

        Args:
            bpy_script: Python script to execute
            output_path: Path to save the exported model
            export_format: glb, fbx, obj, blend
            render_preview: Also render a preview image
            preview_path: Path for preview image

        Returns: dict with paths to generated files
        """
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # Build full script
        full_script = "import bpy\nimport os\nimport math\n\n"
        full_script += bpy_script + "\n\n"

        # Export
        ext = export_format.lower()
        if ext in ("glb", "gltf"):
            full_script += f"\nbpy.ops.export_scene.gltf(filepath=r'{output_path}', export_format='GLB')\n"
        elif ext == "fbx":
            full_script += f"\nbpy.ops.export_scene.fbx(filepath=r'{output_path}')\n"
        elif ext == "obj":
            full_script += f"\nbpy.ops.wm.obj_export(filepath=r'{output_path}')\n"
        elif ext == "blend":
            full_script += f"\nbpy.ops.wm.save_as_mainfile(filepath=r'{output_path}')\n"

        # Render preview
        if render_preview:
            pp = preview_path or output_path.rsplit(".", 1)[0] + "_preview.png"
            full_script += f"""
# Render preview
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 64
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = r'{pp}'
bpy.ops.render.render(write_still=True)
"""

        # Write temp script and run
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".py", dir=os.path.dirname(output_path) or "."
        ) as f:
            f.write(full_script)
            script_path = f.name

        try:
            result = subprocess.run(
                [self.blender_path, "--background", "--factory-startup", "--python", script_path],
                capture_output=True,
                text=True,
                timeout=300,
            )
            logger.info(f"Blender exit code: {result.returncode}")
            if result.returncode != 0:
                logger.warning(f"Blender stderr: {result.stderr[-500:]}")
        finally:
            os.remove(script_path)

        output = {"model": output_path}
        if render_preview and preview_path:
            output["preview"] = preview_path
        if os.path.exists(output_path):
            output["size_kb"] = os.path.getsize(output_path) / 1024
        return output

    # ── Helpers ────────────────────────────────────────────────
    def _clean_script(self, raw):
        """Clean generated script: remove markdown, fix common issues."""
        # Remove markdown code blocks
        raw = re.sub(r"```python\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw)
        # Remove leading/trailing whitespace
        raw = raw.strip()
        # Ensure it starts with import
        if not raw.startswith("import") and not raw.startswith("bpy"):
            # Try to find the start of actual code
            match = re.search(r"(import bpy|bpy\.)", raw)
            if match:
                raw = raw[match.start() :]
        return raw

    def _parse_params(self, text):
        """Extract building parameters from Russian text."""
        p = {
            "width": 10,
            "length": 12,
            "floors": 2,
            "roof_type": "gabled",
            "roof_h": 2.5,
            "wall_r": 0.91,
            "wall_g": 0.88,
            "wall_b": 0.83,
        }
        # Dimensions
        dm = re.search(r"(\d+)\s*[×xх]\s*(\d+)", text)
        if dm:
            p["width"] = int(dm.group(1))
            p["length"] = int(dm.group(2))
        # Floors
        fm = re.search(r"(\d+)\s*(?:этаж|floor)", text)
        if fm:
            p["floors"] = int(fm.group(1))
        for w, n in [("двух", 2), ("трех", 3), ("четыр", 4), ("пяти", 5)]:
            if w in text:
                p["floors"] = n
        # Roof
        if "плоск" in text:
            p["roof_type"] = "flat"
        elif "вальм" in text:
            p["roof_type"] = "hip"
        # Material colors
        if "кирпич" in text:
            p["wall_r"], p["wall_g"], p["wall_b"] = 0.71, 0.40, 0.12
        elif "дерев" in text:
            p["wall_r"], p["wall_g"], p["wall_b"] = 0.55, 0.41, 0.13
        elif "стекл" in text:
            p["wall_r"], p["wall_g"], p["wall_b"] = 0.53, 0.81, 0.92
        return p


# ═══════════════════════════════════════════════════════════════
# QUICK TEST
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    bridge = BlenderLLMBridge(
        model_path=os.environ.get("BLENDERLLM_MODEL", "FreedomIntelligence/BlenderLLM"),
        blender_path=os.environ.get("BLENDER_PATH", "blender"),
        anthropic_key=os.environ.get("ANTHROPIC_API_KEY", ""),
    )

    prompt = sys.argv[1] if len(sys.argv) > 1 else "двухэтажный кирпичный дом 10x12 с двускатной кровлей"
    output = sys.argv[2] if len(sys.argv) > 2 else "output/test_building.glb"

    print(f"[ArchAI] Prompt: {prompt}")
    script = bridge.generate(prompt)
    print(f"[ArchAI] Generated script ({len(script)} chars)")
    print(script[:500] + "..." if len(script) > 500 else script)

    result = bridge.run_in_blender(script, output, render_preview=True)
    print(f"[ArchAI] Result: {json.dumps(result, indent=2)}")
