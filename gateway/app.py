"""
API Gateway — routes requests to microservices (FastAPI)

Endpoints:
  GET  /health, /api/v1/health  — Health check (all services)
  POST /api/v1/generate         — Unified: text → GLB/PNG
  POST /api/v1/parse            — Text → structured params
  POST /api/v1/proxy/claude     — Chat proxy (legacy)

  NEW — Phase 1-5:
  POST /api/v1/analyze/graph    — Spatial graph analysis
  POST /api/v1/analyze/full     — Full building analysis
  POST /api/v1/floorplan/svg    — Generate SVG floor plan
  POST /api/v1/ifc/generate     — Generate IFC file
  POST /api/v1/ifc/parse        — Parse IFC file
  POST /api/v1/ml/classify-style — Style classification
  POST /api/v1/ml/classify-room  — Room type classification
  POST /api/v1/ml/generate-floorplan — Floor plan generation
  POST /api/v1/ml/pointcloud    — Point cloud processing
  POST /api/v1/ml/analyze-image — Image analysis
  CRUD /api/v1/projects         — Project management
  POST /api/v1/search           — Semantic search
  GET  /api/v1/templates        — Building templates

  GET  /docs                     — OpenAPI documentation
"""
import os
import re
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel

app = FastAPI(
    title="Architect Gateway",
    description="API Gateway — маршрутизация к микросервисам",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════
# SERVICE URLS
# ═══════════════════════════════════════════════════════════════

BLENDER_SVC = os.environ.get("BLENDER_SERVICE_URL", "https://ai-arch-blender3d.onrender.com")
LLM_SVC = os.environ.get("LLM_SERVICE_URL", "https://ai-arch-llmproxy.onrender.com")
GEOMETRY_SVC = os.environ.get("GEOMETRY_SERVICE_URL", "https://architect-geometry.onrender.com")
IFC_SVC = os.environ.get("IFC_SERVICE_URL", "https://architect-ifc.onrender.com")
ML_SVC = os.environ.get("ML_SERVICE_URL", "https://architect-ml.onrender.com")
DATA_SVC = os.environ.get("DATA_SERVICE_URL", "https://architect-data.onrender.com")

FRONTEND_DIR = os.environ.get("FRONTEND_DIR", os.path.join(os.path.dirname(__file__), "..", "frontend"))
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
if not os.path.isdir(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join("/", "app", "frontend")


# ═══════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════

class GenerateRequest(BaseModel):
    prompt: str
    object_type: Optional[str] = None
    building_type: str = "house"
    room_type: Optional[str] = None
    floors: int = 2
    width_m: int = 10
    length_m: int = 12
    height_m: int = 3
    style: str = "modern"
    material: str = "plaster"
    roof_type: str = "gabled"
    features: list = []
    furniture: list = []


class ParseRequest(BaseModel):
    text: str


class ChatRequest(BaseModel):
    messages: list
    max_tokens: int = 400
    temperature: float = 0.7
    model: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# RETRY HELPER
# ═══════════════════════════════════════════════════════════════

async def request_with_retry(
    method: str,
    url: str,
    max_retries: int = 2,
    timeout: float = 120.0,
    **kwargs,
) -> httpx.Response:
    """Retry с exponential backoff для Render cold start."""
    last_error = None
    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries + 1):
            try:
                r = await getattr(client, method)(url, timeout=timeout, **kwargs)
                return r
            except httpx.TimeoutException:
                last_error = "timeout"
                if attempt < max_retries:
                    import asyncio
                    await asyncio.sleep(5 * (attempt + 1))
            except httpx.ConnectError:
                last_error = "connection_error"
                if attempt < max_retries:
                    import asyncio
                    await asyncio.sleep(5 * (attempt + 1))
    raise HTTPException(502, f"Service unavailable after {max_retries + 1} attempts: {last_error}")


async def proxy_request(request: Request, target_base: str, path: str):
    """Generic proxy: forward request to target service."""
    data = await request.json()
    r = await request_with_retry(
        "post", f"{target_base}{path}",
        json=data, timeout=60.0
    )
    if r.status_code == 200:
        ct = r.headers.get("content-type", "application/json")
        return Response(content=r.content, media_type=ct)
    raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════

ALL_SERVICES = [
    ("llm", LLM_SVC),
    ("blender", BLENDER_SVC),
    ("geometry", GEOMETRY_SVC),
    ("ifc", IFC_SVC),
    ("ml", ML_SVC),
    ("data", DATA_SVC),
]


@app.get("/health")
@app.get("/api/v1/health")
async def health():
    services = {}
    async with httpx.AsyncClient() as client:
        for name, url in ALL_SERVICES:
            try:
                r = await client.get(f"{url}/health", timeout=5.0)
                services[name] = "ok" if r.status_code == 200 else "error"
            except Exception:
                services[name] = "unreachable"
    return {"status": "ok", "service": "gateway", "version": "3.0.0", "services": services}


# ═══════════════════════════════════════════════════════════════
# CORE GENERATE (existing)
# ═══════════════════════════════════════════════════════════════

INTERIOR_KEYWORDS = [
    "спальн", "детск", "кухн", "гостин", "ванн", "кабинет",
    "салон", "столов", "интерьер", "дизайн интерьера", "комнат",
]


def _detect_gen_type(prompt: str, object_type: Optional[str] = None) -> str:
    if object_type in ("interior", "room"):
        return "interior"
    t = prompt.lower()
    for kw in INTERIOR_KEYWORDS:
        if kw in t:
            return "interior"
    return "building"


@app.post("/api/v1/generate")
async def generate(req: GenerateRequest):
    gen_type = _detect_gen_type(req.prompt, req.object_type)
    target_url = f"{BLENDER_SVC}/api/v1/render/interior" if gen_type == "interior" \
        else f"{BLENDER_SVC}/api/v1/generate/building"

    r = await request_with_retry("post", target_url, json=req.model_dump(), timeout=180.0, max_retries=2)
    if r.status_code == 200:
        return Response(content=r.content, media_type=r.headers.get("content-type", "application/octet-stream"))
    raise HTTPException(r.status_code, detail=r.text)


@app.post("/api/v1/parse")
async def parse(req: ParseRequest):
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(f"{LLM_SVC}/api/v1/parse", json=req.model_dump(), timeout=30.0)
            if r.status_code == 200:
                return r.json()
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.TimeoutException:
            raise HTTPException(504, "LLM parse timeout")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, str(e))


@app.post("/api/v1/proxy/claude")
async def proxy_claude(request: Request):
    data = await request.json()
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(f"{LLM_SVC}/api/v1/chat/completions", json=data, timeout=60.0)
            if r.status_code == 200:
                result = r.json()
                text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"content": [{"type": "text", "text": text or ""}]}
            raise HTTPException(r.status_code, detail=r.text)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, str(e))


@app.post("/api/v1/generate/building")
async def generate_building_legacy(req: GenerateRequest):
    r = await request_with_retry("post", f"{BLENDER_SVC}/api/v1/generate/building", json=req.model_dump(), timeout=180.0, max_retries=2)
    if r.status_code == 200:
        return Response(content=r.content, media_type=r.headers.get("content-type", "application/octet-stream"))
    raise HTTPException(r.status_code, detail=r.text)


@app.post("/api/v1/render/interior")
async def render_interior_legacy(req: GenerateRequest):
    r = await request_with_retry("post", f"{BLENDER_SVC}/api/v1/render/interior", json=req.model_dump(), timeout=180.0, max_retries=2)
    if r.status_code == 200:
        return Response(content=r.content, media_type=r.headers.get("content-type", "application/octet-stream"))
    raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# GEOMETRY SERVICE PROXY
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/analyze/graph")
async def analyze_graph(request: Request):
    return await proxy_request(request, GEOMETRY_SVC, "/api/v1/analyze/graph")


@app.post("/api/v1/analyze/full")
async def analyze_full(request: Request):
    return await proxy_request(request, GEOMETRY_SVC, "/api/v1/analyze/full")


@app.post("/api/v1/floorplan/svg")
async def floorplan_svg(request: Request):
    return await proxy_request(request, GEOMETRY_SVC, "/api/v1/floorplan/svg")


@app.post("/api/v1/analyze/path")
async def analyze_path(request: Request):
    return await proxy_request(request, GEOMETRY_SVC, "/api/v1/analyze/path")


# ═══════════════════════════════════════════════════════════════
# IFC SERVICE PROXY
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/ifc/generate")
async def ifc_generate(request: Request):
    return await proxy_request(request, IFC_SVC, "/api/v1/ifc/generate")


@app.post("/api/v1/ifc/parse")
async def ifc_parse(request: Request):
    return await proxy_request(request, IFC_SVC, "/api/v1/ifc/parse")


@app.post("/api/v1/ifc/convert")
async def ifc_convert(request: Request):
    return await proxy_request(request, IFC_SVC, "/api/v1/ifc/convert")


# ═══════════════════════════════════════════════════════════════
# ML SERVICE PROXY
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/ml/classify-style")
async def ml_classify_style(request: Request):
    return await proxy_request(request, ML_SVC, "/api/v1/ml/classify-style")


@app.post("/api/v1/ml/classify-room")
async def ml_classify_room(request: Request):
    return await proxy_request(request, ML_SVC, "/api/v1/ml/classify-room")


@app.post("/api/v1/ml/generate-floorplan")
async def ml_generate_floorplan(request: Request):
    return await proxy_request(request, ML_SVC, "/api/v1/ml/generate-floorplan")


@app.post("/api/v1/ml/pointcloud")
async def ml_pointcloud(request: Request):
    return await proxy_request(request, ML_SVC, "/api/v1/ml/pointcloud")


@app.post("/api/v1/ml/analyze-image")
async def ml_analyze_image(request: Request):
    return await proxy_request(request, ML_SVC, "/api/v1/ml/analyze-image")


# ═══════════════════════════════════════════════════════════════
# DATA SERVICE PROXY
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/projects")
async def create_project(request: Request):
    return await proxy_request(request, DATA_SVC, "/api/v1/projects")


@app.get("/api/v1/projects/{project_id}")
async def get_project(project_id: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{DATA_SVC}/api/v1/projects/{project_id}", timeout=15.0)
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, detail=r.text)


@app.get("/api/v1/projects")
async def list_projects(limit: int = 50, offset: int = 0):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{DATA_SVC}/api/v1/projects?limit={limit}&offset={offset}", timeout=15.0)
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, detail=r.text)


@app.put("/api/v1/projects/{project_id}")
async def update_project(project_id: str, request: Request):
    data = await request.json()
    async with httpx.AsyncClient() as client:
        r = await client.put(f"{DATA_SVC}/api/v1/projects/{project_id}", json=data, timeout=15.0)
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, detail=r.text)


@app.delete("/api/v1/projects/{project_id}")
async def delete_project(project_id: str):
    async with httpx.AsyncClient() as client:
        r = await client.delete(f"{DATA_SVC}/api/v1/projects/{project_id}", timeout=15.0)
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, detail=r.text)


@app.post("/api/v1/search")
async def search_projects(request: Request):
    return await proxy_request(request, DATA_SVC, "/api/v1/search")


@app.get("/api/v1/templates")
async def list_templates():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{DATA_SVC}/api/v1/templates", timeout=15.0)
        if r.status_code == 200:
            return r.json()
        raise HTTPException(r.status_code, detail=r.text)


# ═══════════════════════════════════════════════════════════════
# STATIC FILES
# ═══════════════════════════════════════════════════════════════

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/{filename:path}")
async def serve_static(filename: str):
    path = os.path.join(FRONTEND_DIR, filename)
    if os.path.isfile(path):
        return FileResponse(path)
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    print(f"Gateway starting on port {port}")
    print(f"Services: LLM={LLM_SVC}, Blender={BLENDER_SVC}")
    print(f"          Geometry={GEOMETRY_SVC}, IFC={IFC_SVC}")
    print(f"          ML={ML_SVC}, Data={DATA_SVC}")
    uvicorn.run(app, host="0.0.0.0", port=port)
