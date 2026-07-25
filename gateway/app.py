"""
API Gateway
"""
import os
import httpx
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BLENDER_SVC = os.environ.get("BLENDER_SERVICE_URL", "http://localhost:8082")
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

# OpenRouter config
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OR_BASE = "https://openrouter.ai/api/v1"
OR_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"


@app.route("/health")
@app.route("/api/v1/health")
def health():
    services = {"blender": "unknown"}
    try:
        r = httpx.get(f"{BLENDER_SVC}/health", timeout=5.0)
        services["blender"] = "ok" if r.status_code == 200 else "error"
    except:
        services["blender"] = "unreachable"
    return jsonify({"status": "ok", "service": "gateway", "services": services})


@app.route("/api/v1/proxy/claude", methods=["POST"])
def proxy_claude():
    data = request.json or {}
    messages = data.get("messages", [])
    max_tokens = data.get("max_tokens", 400)
    headers = {"Content-Type": "application/json", "HTTP-Referer": "https://archai.app", "X-Title": "Architect"}
    if OR_KEY:
        headers["Authorization"] = f"Bearer {OR_KEY}"
    try:
        r = httpx.post(
            f"{OR_BASE}/chat/completions",
            headers=headers,
            json={"model": OR_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7},
            timeout=60.0,
        )
        if r.status_code == 200:
            text = r.json()["choices"][0]["message"]["content"]
            return jsonify({"content": [{"type": "text", "text": text or ""}]}), 200
        return jsonify({"error": str(r.text)}), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/v1/generate/building", methods=["POST"])
def generate_building():
    try:
        r = httpx.post(f"{BLENDER_SVC}/api/v1/generate/building", json=request.json, timeout=120.0)
        if r.status_code == 200:
            return r.content, 200, {"Content-Type": "model/gltf-binary"}
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/v1/render/interior", methods=["POST"])
def render_interior():
    try:
        r = httpx.post(f"{BLENDER_SVC}/api/v1/render/interior", json=request.json, timeout=300.0)
        if r.status_code == 200:
            return r.content, 200, {"Content-Type": "image/png"}
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(FRONTEND_DIR, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Gateway starting on port {port}")
    print(f"Blender: {BLENDER_SVC}")
    app.run(host="0.0.0.0", port=port, debug=False)
