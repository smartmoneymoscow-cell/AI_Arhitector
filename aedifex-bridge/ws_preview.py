"""
aedifex-bridge/ws_preview.py — WebSocket real-time preview.

aedifex редактор → WebSocket → Bridge → Blender Service → preview image → обратно

Позволяет видеть превью рендера в реальном времени при редактировании.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any

import httpx
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("ws_preview")

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")
BLENDER_SERVICE_URL = os.environ.get("BLENDER_SERVICE_URL", "http://localhost:8082")
PREVIEW_QUALITY = os.environ.get("PREVIEW_QUALITY", "quick")  # quick for real-time
PREVIEW_RESOLUTION = os.environ.get("PREVIEW_RESOLUTION", "1024x768")

app = FastAPI(title="Aedifex WebSocket Preview")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ═══════════════════════════════════════════════════════════════
# Connection manager
# ═══════════════════════════════════════════════════════════════


class PreviewConnection:
    """Single WebSocket connection for real-time preview."""

    def __init__(self, ws: WebSocket, client_id: str):
        self.ws = ws
        self.client_id = client_id
        self.last_scene: dict | None = None
        self.last_preview_time: float = 0
        self.preview_debounce: float = 0.5  # seconds
        self.is_rendering: bool = False
        self.current_job_id: str | None = None

    async def send_json(self, data: dict):
        try:
            await self.ws.send_json(data)
        except Exception:
            pass

    async def send_image(self, image_data: bytes, job_id: str):
        """Send preview image as binary frame."""
        try:
            # Header: job_id as JSON, then binary image
            header = json.dumps({"type": "preview", "job_id": job_id}).encode()
            await self.ws.send_bytes(len(header).to_bytes(4, "big") + header + image_data)
        except Exception:
            pass


class ConnectionManager:
    """Manages all WebSocket connections."""

    def __init__(self):
        self.connections: dict[str, PreviewConnection] = {}

    async def connect(self, ws: WebSocket, client_id: str) -> PreviewConnection:
        await ws.accept()
        conn = PreviewConnection(ws, client_id)
        self.connections[client_id] = conn
        logger.info(f"Client connected: {client_id}")
        return conn

    def disconnect(self, client_id: str):
        self.connections.pop(client_id, None)
        logger.info(f"Client disconnected: {client_id}")

    def get_connection(self, client_id: str) -> PreviewConnection | None:
        return self.connections.get(client_id)


manager = ConnectionManager()


# ═══════════════════════════════════════════════════════════════
# WebSocket endpoint
# ═══════════════════════════════════════════════════════════════


@app.websocket("/ws/preview/{client_id}")
async def websocket_preview(ws: WebSocket, client_id: str):
    """
    Real-time preview WebSocket.
    
    Protocol:
    - Client sends: {"type": "scene_update", "scene": {...}}
    - Server sends: {"type": "preview", "job_id": "..."} + binary image data
    - Server sends: {"type": "status", "rendering": true/false}
    - Server sends: {"type": "error", "message": "..."}
    """
    conn = await manager.connect(ws, client_id)

    try:
        # Send initial status
        await conn.send_json({"type": "connected", "client_id": client_id})

        while True:
            data = await ws.receive_json()

            if data.get("type") == "scene_update":
                scene = data.get("scene", {})
                conn.last_scene = scene

                # Debounce: don't render too frequently
                now = time.time()
                if now - conn.last_preview_time < conn.preview_debounce:
                    continue

                if conn.is_rendering:
                    # Skip if already rendering
                    continue

                conn.last_preview_time = now
                conn.is_rendering = True

                # Send rendering status
                await conn.send_json({"type": "status", "rendering": True})

                # Start async render
                job_id = uuid.uuid4().hex[:8]
                conn.current_job_id = job_id

                asyncio.create_task(
                    render_preview(conn, scene, job_id)
                )

            elif data.get("type") == "cancel":
                conn.is_rendering = False
                await conn.send_json({"type": "status", "rendering": False})

            elif data.get("type") == "ping":
                await conn.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        manager.disconnect(client_id)


# ═══════════════════════════════════════════════════════════════
# Render preview
# ═══════════════════════════════════════════════════════════════


async def render_preview(conn: PreviewConnection, scene: dict, job_id: str):
    """Render preview through Blender Service."""
    try:
        # Convert scene to Blender params
        render_params = scene_to_blender_params(scene, job_id)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{BLENDER_SERVICE_URL}/preview",
                json=render_params,
            )
            resp.raise_for_status()
            result = resp.json()

        # Get preview image URL
        image_url = result.get("image_url") or result.get("preview_url")
        if image_url:
            # Download image
            async with httpx.AsyncClient(timeout=30) as client:
                img_resp = await client.get(image_url)
                if img_resp.status_code == 200:
                    await conn.send_image(img_resp.content, job_id)

        await conn.send_json({
            "type": "preview_complete",
            "job_id": job_id,
            "image_url": image_url,
        })

    except Exception as e:
        logger.error(f"Preview render failed: {e}")
        await conn.send_json({"type": "error", "message": str(e)})

    finally:
        conn.is_rendering = False
        await conn.send_json({"type": "status", "rendering": False})


def scene_to_blender_params(scene: dict, job_id: str) -> dict:
    """Convert aedifex scene to Blender preview params."""
    walls = []
    windows = []
    doors = []
    materials = []

    nodes = scene.get("nodes", {})
    for node_id, node in nodes.items():
        node_type = node.get("type")

        if node_type == "wall":
            walls.append({
                "start": node.get("start", [0, 0]),
                "end": node.get("end", [0, 0]),
                "thickness": node.get("thickness", 0.3),
                "height": node.get("height", 3.0),
            })
        elif node_type == "window":
            windows.append({
                "width": node.get("width", 1.0),
                "height": node.get("height", 1.2),
                "position": node.get("position", [0, 0, 0]),
            })
        elif node_type == "door":
            doors.append({
                "width": node.get("width", 0.9),
                "height": node.get("height", 2.1),
                "position": node.get("position", [0, 0, 0]),
            })

    return {
        "job_id": f"preview_{job_id}",
        "gen_type": "building",
        "params": {
            "walls": walls,
            "windows": windows,
            "doors": doors,
        },
        "quality": PREVIEW_QUALITY,
        "resolution": PREVIEW_RESOLUTION,
        "preview_mode": True,
    }


# ═══════════════════════════════════════════════════════════════
# REST fallback (non-WebSocket clients)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/preview/quick")
async def quick_preview(scene: dict):
    """Quick preview without WebSocket — returns image URL."""
    job_id = uuid.uuid4().hex[:8]
    render_params = scene_to_blender_params(scene, job_id)

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(
                f"{BLENDER_SERVICE_URL}/preview",
                json=render_params,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"error": str(e), "job_id": job_id}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ws-preview"}
