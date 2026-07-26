"""
API Gateway — routes requests to microservices
"""
import os
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BLENDER_SVC = os.environ.get("BLENDER_SERVICE_URL", "http://localhost:8082")
LLM_SVC = os.environ.get("LLM_SERVICE_URL", "https://ai-arch-llmproxy.onrender.com")
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
# Docker fallback: if ../frontend doesn't exist, try /app/frontend
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join("/", "app", "frontend")


@app.route("/health")
@app.route("/api/v1/health")
def health():
    services = {}
    for name, url in [("llm", LLM_SVC), ("blender", BLENDER_SVC)]:
        try:
            r = requests.get(f"{url}/health", timeout=5)
            services[name] = "ok" if r.status_code == 200 else "error"
        except:
            services[name] = "unreachable"
    return jsonify({"status": "ok", "service": "gateway", "services": services})


@app.route("/api/v1/proxy/claude", methods=["POST"])
def proxy_claude():
    try:
        r = requests.post(f"{LLM_SVC}/api/v1/chat/completions", json=request.json, timeout=60)
        r.encoding = "utf-8"
        if r.status_code == 200:
            result = r.json()
            text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return jsonify({"content": [{"type": "text", "text": text or ""}]}), 200
        return jsonify({"error": r.json()}), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/v1/generate/building", methods=["POST"])
def generate_building():
    try:
        r = requests.post(f"{BLENDER_SVC}/api/v1/generate/building", json=request.json, timeout=120)
        if r.status_code == 200:
            return r.content, 200, {"Content-Type": "model/gltf-binary"}
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/v1/render/interior", methods=["POST"])
def render_interior():
    try:
        r = requests.post(f"{BLENDER_SVC}/api/v1/render/interior", json=request.json, timeout=300)
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
    print(f"LLM: {LLM_SVC}")
    print(f"Blender: {BLENDER_SVC}")
    app.run(host="0.0.0.0", port=port, debug=False)
