"""
LLM Microservice — proxy to OpenRouter
"""
import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OR_BASE = "https://openrouter.ai/api/v1"
MODEL = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "llm-service", "model": MODEL})


@app.route("/api/v1/chat/completions", methods=["POST"])
def chat_completions():
    data = request.json or {}
    messages = data.get("messages", [])
    max_tokens = data.get("max_tokens", 400)
    temperature = data.get("temperature", 0.7)
    model = data.get("model", MODEL)

    headers = {"Content-Type": "application/json", "HTTP-Referer": "https://archai.app", "X-Title": "Architect LLM"}
    if OR_KEY:
        headers["Authorization"] = f"Bearer {OR_KEY}"

    try:
        r = requests.post(
            f"{OR_BASE}/chat/completions",
            headers=headers,
            json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
            timeout=60,
        )
        r.encoding = "utf-8"
        if r.status_code == 200:
            return jsonify(r.json()), 200
        try:
            return jsonify(r.json()), r.status_code
        except:
            return jsonify({"error": "OpenRouter API error", "status": r.status_code}), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    print(f"LLM Service starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
