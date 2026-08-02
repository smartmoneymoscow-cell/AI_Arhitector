"""
aedifex-bridge/main.py — Единая точка входа для всех bridge-сервисов.

Объединяет:
- bridge.py — REST API мост между aedifex и AI_Arhitector микросервисами
- ws_preview.py — WebSocket real-time preview
- mcp_llm_bridge.py — MCP ↔ LLM Service интеграция

Запуск: python main.py
"""

import logging
import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import all sub-apps
from bridge import app as bridge_app
from ws_preview import app as ws_app
from mcp_llm_bridge import app as mcp_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aedifex-bridge-main")

PORT = int(os.environ.get("BRIDGE_PORT", "8085"))

# ═══════════════════════════════════════════════════════════════
# Combined FastAPI app
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="Aedifex Bridge — Unified",
    description="""
    Unified bridge between aedifex 3D editor and AI_Arhitector microservices.
    
    ## Endpoints
    
    ### REST API (bridge.py)
    - `POST /api/v1/generate-to-scene` — Prompt → 3D scene
    - `POST /api/v1/export/ifc` — Export to IFC
    - `POST /api/v1/import/dxf` — Import DXF
    - `POST /api/v1/render` — Blender render
    - `POST /api/v1/parametric/wall` — Parametric wall
    
    ### WebSocket (ws_preview.py)
    - `WS /ws/preview/{client_id}` — Real-time preview
    
    ### MCP-LLM (mcp_llm_bridge.py)
    - `POST /api/v1/mcp/ai-edit` — AI editing
    - `POST /api/v1/mcp/chat` — Conversational editing
    - `GET /api/v1/mcp/tools` — List MCP tools
    """,
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount sub-apps
app.mount("/bridge", bridge_app)
app.mount("/preview", ws_app)
app.mount("/mcp", mcp_app)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "aedifex-bridge-unified",
        "version": "1.0.0",
        "components": {
            "bridge": "active",
            "ws_preview": "active",
            "mcp_llm": "active",
        },
    }


@app.get("/")
async def root():
    return {
        "name": "Aedifex Bridge",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "bridge": "/bridge/api/v1/",
            "preview": "/preview/ws/preview/{client_id}",
            "mcp": "/mcp/api/v1/mcp/",
        },
    }


if __name__ == "__main__":
    logger.info(f"Starting Aedifex Bridge on port {PORT}")
    logger.info("Components: bridge + ws_preview + mcp_llm_bridge")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
