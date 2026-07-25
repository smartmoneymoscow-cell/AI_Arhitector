"""
API Gateway — маршрутизация запросов к микросервисам
- /health → self
- /api/v1/proxy/claude → LLM Service
- /api/v1/generate/building → Blender Service
- /api/v1/render/interior → Blender Service
- /* → статика (фронтенд)
"""
import os
import httpx
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

LLM_SERVICE = os.environ.get("LLM_SERVICE_URL", "http://localhost:8081")
BLENDER_SERVICE = os.environ.get("BLENDER_SERVICE_URL", "http://localhost:8082")
FRONTEND_DIR = os.environ.get("FRONTEND_DIR", os.path.join(os.path.dirname(__file__), "..", "frontend"))


@app.route("/health")
@app.route("/api/v1/health")
def health():
    # Check all services
    services = {}
    for name, url in [("llm", LLM_SERVICE), ("blender", BLENDER_SERVICE)]:
        try:
            r = httpx.get(f"{url}/health", timeout=5.0)
            services[name] = "ok" if r.status_code == 200 else "error"
        except:
            services[name] = "unreachable"
    return jsonify({"status": "ok", "service": "gateway", "services": services})


@app.route("/api/v1/proxy/claude", methods=["POST"])
def proxy_claude():
    """Проксирует LLM-запросы к LLM Service."""
    data = request.json or {}
    try:
        r = httpx.post(
            f"{LLM_SERVICE}/api/v1/chat/completions",
            json=data,
            timeout=60.0,
        )
        if r.status_code == 200:
            result = r.json()
            choices = result.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
            else:
                content = ""
            return jsonify({"content": [{"type": "text", "text": content or ""}]}), 200
        return jsonify({"error": r.text}), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/v1/generate/building", methods=["POST"])
def generate_building():
    """Проксирует запрос генерации здания к Blender Service."""
    try:
        r = httpx.post(
            f"{BLENDER_SERVICE}/api/v1/generate/building",
            json=request.json,
            timeout=120.0,
        )
        if r.status_code == 200:
            return r.content, 200, {"Content-Type": r.headers.get("Content-Type", "model/gltf-binary")}
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/v1/render/interior", methods=["POST"])
def render_interior():
    """Проксирует запрос рендера интерьера к Blender Service."""
    try:
        r = httpx.post(
            f"{BLENDER_SERVICE}/api/v1/render/interior",
            json=request.json,
            timeout=300.0,
        )
        if r.status_code == 200:
            return r.content, 200, {"Content-Type": r.headers.get("Content-Type", "image/png")}
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


# Static frontend
@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(FRONTEND_DIR, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Gateway starting on port {port}")
    print(f"   LLM Service: {LLM_SERVICE}")
    print(f"   Blender Service: {BLENDER_SERVICE}")
    app.run(host="0.0.0.0", port=port, debug=False)
