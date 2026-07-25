"""
LLM Microservice — прокси к OpenRouter
Эндпоинт: POST /api/v1/chat/completions
"""
import os
import sys
import httpx
from flask import Flask, request, jsonify
from flask_cors import CORS

# Force UTF-8 encoding
import locale
try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except:
    pass
os.environ['PYTHONIOENCODING'] = 'utf-8

app = Flask(__name__)
CORS(app)

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
MODEL = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "llm-service", "model": MODEL})


@app.route("/api/v1/chat/completions", methods=["POST"])
def chat_completions():
    """Прокси к OpenRouter — принимает OpenAI-формат."""
    data = request.json or {}
    messages = data.get("messages", [])
    max_tokens = data.get("max_tokens", 400)
    temperature = data.get("temperature", 0.7)
    model = data.get("model", MODEL)

    headers = {
        "Content-Type": "application/json",
        "HTTP-Referer": "https://archai.app",
        "X-Title": "Architect LLM",
    }
    if OPENROUTER_KEY:
        headers["Authorization"] = f"Bearer {OPENROUTER_KEY}"

    try:
        r = httpx.post(
            f"{OPENROUTER_BASE}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=60.0,
        )
        if r.status_code == 200:
            result = r.json()
            return jsonify(result), 200
        return jsonify({"error": r.text.encode("utf-8", errors="replace").decode("utf-8")}), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    print(f"🤖 LLM Service starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
