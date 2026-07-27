"""
API Gateway — routes requests to microservices

Endpoints:
  GET  /health, /api/v1/health  — Health check (checks LLM + Blender)
  POST /api/v1/generate         — Unified: text → GLB/PNG (proxies to Blender)
  POST /api/v1/parse            — Text → structured params (proxies to LLM)
  POST /api/v1/proxy/claude     — Chat proxy (legacy)
  POST /api/v1/generate/building — Building gen (legacy)
  POST /api/v1/render/interior   — Interior render (legacy)
"""
import os
import time
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BLENDER_SVC = os.environ.get("BLENDER_SERVICE_URL", "http://localhost:8082")
LLM_SVC = os.environ.get("LLM_SERVICE_URL", "http://localhost:8081")
FRONTEND_DIR = os.environ.get("FRONTEND_DIR", os.path.join(os.path.dirname(__file__), "..", "frontend"))
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join("/", "app", "frontend")


def request_with_retry(method, url, max_retries=2, **kwargs):
    """Retry с exponential backoff для Render cold start."""
    kwargs.setdefault("timeout", kwargs.get("timeout", 120))
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            r = getattr(requests, method)(url, **kwargs)
            return r
        except requests.exceptions.Timeout:
            last_error = "timeout"
            if attempt < max_retries:
                time.sleep(5 * (attempt + 1))
                continue
        except requests.exceptions.ConnectionError:
            last_error = "connection_error"
            if attempt < max_retries:
                time.sleep(5 * (attempt + 1))
                continue
    raise Exception(f"Service unavailable after {max_retries + 1} attempts: {last_error}")


# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════

@app.route("/health")
@app.route("/api/v1/health")
def health():
    services = {}
    for name, url in [("llm", LLM_SVC), ("blender", BLENDER_SVC)]:
        try:
            r = requests.get(f"{url}/health", timeout=5)
            services[name] = "ok" if r.status_code == 200 else "error"
        except Exception:
            services[name] = "unreachable"
    return jsonify({"status": "ok", "service": "gateway", "services": services})


# ═══════════════════════════════════════════════════════════════
# UNIFIED GENERATE (Step 1.2 + 1.5 retry)
# ═══════════════════════════════════════════════════════════════

@app.route("/api/v1/generate", methods=["POST"])
def generate():
    """
    Единый endpoint генерации.
    Проксирует запрос к blender-service /api/v1/generate.
    Retry при cold start (502/timeout).
    """
    data = request.json or {}
    if not data.get("prompt"):
        return jsonify({"error": "prompt required"}), 400

    try:
        r = request_with_retry(
            "post",
            f"{BLENDER_SVC}/api/v1/generate",
            json=data,
            timeout=180,
            max_retries=2,
        )
        if r.status_code == 200:
            content_type = r.headers.get("Content-Type", "application/octet-stream")
            return r.content, 200, {"Content-Type": content_type}
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


# ═══════════════════════════════════════════════════════════════
# PARSE (Step 1.2 — proxy to LLM service)
# ═══════════════════════════════════════════════════════════════

@app.route("/api/v1/parse", methods=["POST"])
def parse():
    """
    Парсинг промта → структурированные параметры.
    Проксирует к llm-service /api/v1/parse.
    """
    data = request.json or {}
    if not data.get("text"):
        return jsonify({"error": "text required"}), 400

    try:
        r = requests.post(f"{LLM_SVC}/api/v1/parse", json=data, timeout=30)
        if r.status_code == 200:
            return jsonify(r.json()), 200
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


# ═══════════════════════════════════════════════════════════════
# LEGACY ENDPOINTS (backward compatibility)
# ═══════════════════════════════════════════════════════════════

@app.route("/api/v1/proxy/claude", methods=["POST"])
def proxy_claude():
    """Legacy: proxy chat to LLM service."""
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
    """Legacy: building generation via /api/v1/generate."""
    data = request.json or {}
    data.setdefault("object_type", "building")
    try:
        r = request_with_retry(
            "post",
            f"{BLENDER_SVC}/api/v1/generate",
            json=data,
            timeout=180,
            max_retries=2,
        )
        if r.status_code == 200:
            return r.content, 200, {"Content-Type": "model/gltf-binary"}
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/v1/render/interior", methods=["POST"])
def render_interior():
    """Legacy: interior render via /api/v1/generate."""
    data = request.json or {}
    data.setdefault("object_type", "interior")
    try:
        r = request_with_retry(
            "post",
            f"{BLENDER_SVC}/api/v1/generate",
            json=data,
            timeout=300,
            max_retries=2,
        )
        if r.status_code == 200:
            return r.content, 200, {"Content-Type": "image/png"}
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


# ═══════════════════════════════════════════════════════════════
# STATIC FILES
# ═══════════════════════════════════════════════════════════════

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
