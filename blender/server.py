"""
ArchAI Blender Server
Flask API that connects the web interface to Blender generation.

Endpoints:
    GET  /health                        — Health check
    POST /api/v1/generate/building      — Generate 3D building from text
    POST /api/v1/render/interior        — Render photorealistic interior
    POST /api/v1/generate/script        — Generate bpy script only (no Blender)

Requires: Blender installed, BlenderLLM model or ANTHROPIC_API_KEY
"""

import json
import logging
import os
import subprocess
import sys
import uuid

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

# Add blender scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "blender"))
from blenderllm_bridge import BlenderLLMBridge

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
BLENDER_PATH = os.environ.get("BLENDER_PATH", "blender")
MODEL_PATH = os.environ.get("BLENDERLLM_MODEL", "FreedomIntelligence/BlenderLLM")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
PORT = int(os.environ.get("PORT", 5000))

os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("archai.server")

# ═══════════════════════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════════════════════
app = Flask(__name__)
CORS(app)

bridge = BlenderLLMBridge(
    model_path=MODEL_PATH,
    blender_path=BLENDER_PATH,
    anthropic_key=ANTHROPIC_KEY,
    anthropic_base=ANTHROPIC_BASE,
)


# Try loading model on startup (non-blocking if fails)
def _load_model_async():
    try:
        bridge.load_model()
    except Exception as e:
        logger.warning(f"Model not loaded (will use Claude fallback): {e}")


import threading

threading.Thread(target=_load_model_async, daemon=True).start()

# ═══════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════


@app.route("/health")
@app.route("/api/v1/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "service": "archai-blender",
            "model_loaded": bridge._model_loaded,
            "blender": BLENDER_PATH,
        }
    )


@app.route("/api/v1/generate/script", methods=["POST"])
def generate_script():
    """Generate bpy script from text (no Blender execution)."""
    data = request.json or {}
    prompt = data.get("prompt", "")
    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    try:
        script = bridge.generate(prompt)
        return jsonify(
            {
                "script": script,
                "prompt": prompt,
                "chars": len(script),
            }
        )
    except Exception as e:
        logger.error(f"Script generation failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/generate/building", methods=["POST"])
def generate_building():
    """Generate 3D building model from text prompt.

    Body JSON:
        prompt: str — Natural language description
        export_format: str — glb, fbx, obj, blend (default: glb)
        render_preview: bool — Also render preview image
    """
    data = request.json or {}
    prompt = data.get("prompt", "")
    export_format = data.get("export_format", "glb")
    render_preview = data.get("render_preview", False)

    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    job_id = uuid.uuid4().hex[:8]
    output_file = os.path.join(OUTPUT_DIR, f"{job_id}.{export_format}")
    preview_file = os.path.join(OUTPUT_DIR, f"{job_id}_preview.png") if render_preview else None

    try:
        # Generate bpy script
        logger.info(f"[{job_id}] Generating script for: {prompt[:80]}")
        script = bridge.generate(prompt)

        # Run in Blender
        logger.info(f"[{job_id}] Running in Blender, export={export_format}")
        result = bridge.run_in_blender(
            script,
            output_file,
            export_format=export_format,
            render_preview=render_preview,
            preview_path=preview_file,
        )

        result["job_id"] = job_id
        result["prompt"] = prompt
        result["script_chars"] = len(script)

        if os.path.exists(output_file):
            return send_file(
                output_file,
                as_attachment=True,
                download_name=f"archai_{job_id}.{export_format}",
                mimetype="model/gltf-binary" if export_format == "glb" else None,
            )
        else:
            return jsonify({"error": "Generation failed", "details": result}), 500

    except Exception as e:
        logger.error(f"[{job_id}] Generation error: {e}")
        return jsonify({"error": str(e), "job_id": job_id}), 500


@app.route("/api/v1/render/interior", methods=["POST"])
def render_interior():
    """Render photorealistic interior.

    Body JSON:
        room_type: str — living_room, bedroom, kitchen, office
        width, length, height: float — room dimensions
        style: str — modern, classic, scandinavian, loft, minimalist
        furniture: list — sofa, table, bed, chandelier
    """
    data = request.json or {}
    job_id = uuid.uuid4().hex[:8]
    params_file = os.path.join(OUTPUT_DIR, f"{job_id}_interior.json")
    output_file = os.path.join(OUTPUT_DIR, f"{job_id}_interior.png")

    with open(params_file, "w") as f:
        json.dump(data, f)

    interior_script = os.path.join(os.path.dirname(__file__), "blender", "render_interior.py")

    try:
        result = subprocess.run(
            [
                BLENDER_PATH,
                "--background",
                "--factory-startup",
                "--python",
                interior_script,
                "--",
                params_file,
                output_file,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if os.path.exists(output_file):
            return send_file(
                output_file,
                as_attachment=True,
                download_name=f"archai_interior_{job_id}.png",
            )
        else:
            return jsonify(
                {
                    "error": "Render failed",
                    "stderr": result.stderr[-500:],
                }
            ), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════
# STATIC FILES (serve frontend)
# ═══════════════════════════════════════════════════════════════
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")


@app.route("/")
def serve_index():
    index = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index):
        return send_file(index)
    return jsonify({"error": "Frontend not found"}), 404


# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    logger.info(f"Starting ArchAI Blender Server on port {PORT}")
    logger.info(f"Blender: {BLENDER_PATH}")
    logger.info(f"Model: {MODEL_PATH}")
    logger.info(f"Output: {OUTPUT_DIR}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
