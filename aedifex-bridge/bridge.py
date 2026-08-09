"""
aedifex-bridge/bridge.py — Мост между aedifex MCP и AI_Arhitector Gateway.

aedifex редактор → MCP tools → Bridge → Gateway API → существующие микросервисы
                                                  → LLM Service (парсинг промтов)
                                                  → Blender Service (рендер)
                                                  → IFC Service (экспорт BIM)

НЕ нарушает существующий orchestrator — работает через REST API.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")
LLM_SERVICE_URL = os.environ.get("LLM_SERVICE_URL", "http://localhost:8081")
IFC_SERVICE_URL = os.environ.get("IFC_SERVICE_URL", "http://localhost:8083")
CAD_SERVICE_URL = os.environ.get("CAD_SERVICE_URL", "http://localhost:8084")
BLENDER_SERVICE_URL = os.environ.get("BLENDER_SERVICE_URL", "http://localhost:8082")
PORT = int(os.environ.get("BRIDGE_PORT", "8085"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aedifex-bridge")

app = FastAPI(
    title="Aedifex Bridge",
    description="Мост между aedifex 3D редактором и AI_Arhitector микросервисами",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# Models
# ═══════════════════════════════════════════════════════════════


class AedifexScene(BaseModel):
    """Сцена aedifex в формате JSON."""
    nodes: dict[str, Any] = Field(default_factory=dict)
    rootNodeIds: list[str] = Field(default_factory=list)
    collections: dict[str, Any] | None = None


class GenerateFromPromptRequest(BaseModel):
    """Запрос на генерацию из промта через AI + aedifex."""
    prompt: str
    profile: str = "standard"  # quick | standard | full | premium | interior
    language: str = "ru"


class ExportRequest(BaseModel):
    """Запрос на экспорт сцены."""
    scene: AedifexScene
    format: str = "ifc"  # ifc | glb | step | dxf | svg


class RenderRequest(BaseModel):
    """Запрос на рендер через Blender."""
    scene: AedifexScene
    quality: str = "standard"  # quick | standard | premium
    resolution: str = "4K"  # 4K | 16K


class DXFImportRequest(BaseModel):
    """Запрос на импорт DXF."""
    convert_to_walls: bool = True
    wall_height: float = 3.0
    wall_thickness: float = 0.3


# ═══════════════════════════════════════════════════════════════
# Health
# ═══════════════════════════════════════════════════════════════


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aedifex-bridge", "version": "1.0.0"}


@app.get("/health/services")
async def health_services():
    """Проверка доступности всех микросервисов."""
    services = {
        "gateway": GATEWAY_URL,
        "llm": LLM_SERVICE_URL,
        "ifc": IFC_SERVICE_URL,
        "cad": CAD_SERVICE_URL,
        "blender": BLENDER_SERVICE_URL,
    }
    results = {}
    async with httpx.AsyncClient(timeout=5) as client:
        for name, url in services.items():
            try:
                r = await client.get(f"{url}/health")
                results[name] = {"status": "ok" if r.status_code == 200 else "error", "url": url}
            except Exception as e:
                results[name] = {"status": "unreachable", "error": str(e)[:100], "url": url}
    return results


# ═══════════════════════════════════════════════════════════════
# 1. AI Prompt → Aedifex Scene (через LLM Service + MCP)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/generate-to-scene")
async def generate_to_scene(req: GenerateFromPromptRequest):
    """
    Генерация 3D сцены из текстового промта.
    
    Pipeline:
    1. LLM Service парсит промт → параметры здания
    2. Bridge конвертирует параметры → aedifex scene (MCP operations)
    3. Возвращает scene JSON для отображения в редакторе
    """
    job_id = uuid.uuid4().hex[:12]
    logger.info(f"[{job_id}] Generating scene from prompt: {req.prompt[:80]}...")

    # Шаг 1: Парсинг через LLM Service
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            llm_resp = await client.post(
                f"{LLM_SERVICE_URL}/parse",
                json={"prompt": req.prompt, "language": req.language},
            )
            llm_resp.raise_for_status()
            params = llm_resp.json()
        except Exception as e:
            logger.error(f"[{job_id}] LLM parse failed: {e}")
            # Fallback на regex парсинг
            params = _regex_fallback(req.prompt)

    logger.info(f"[{job_id}] Parsed params: {json.dumps(params, ensure_ascii=False)[:200]}")

    # Шаг 2: Конвертация параметров → aedifex scene
    scene = _params_to_aedifex_scene(params, job_id)

    return {
        "job_id": job_id,
        "status": "ok",
        "scene": scene,
        "params": params,
        "message": f"Сцена создана: {params.get('gen_type', 'building')}",
    }


def _regex_fallback(prompt: str) -> dict:
    """Regex fallback для парсинга промта (копия из shared/parser.py)."""
    import re
    
    result = {
        "gen_type": "building",
        "width": 10,
        "length": 12,
        "floors": 1,
        "wall_height": 3.0,
        "style": "modern",
        "material": "brick",
        "features": [],
    }
    
    prompt_lower = prompt.lower()
    
    # Определение типа
    interior_kw = ["кухня", "ванная", "спальня", "гостиная", "прихожая", "интерьер", "комната"]
    if any(kw in prompt_lower for kw in interior_kw):
        result["gen_type"] = "interior"
    
    # Размеры
    dims = re.findall(r'(\d+(?:\.\d+)?)\s*[x×х*]\s*(\d+(?:\.\d+)?)', prompt)
    if dims:
        result["width"] = float(dims[0][0])
        result["length"] = float(dims[0][1])
    
    # Этажность
    floors = re.findall(r'(\d+)\s*(?:этаж|этажн)', prompt_lower)
    if floors:
        result["floors"] = int(floors[0])
    
    # Стиль
    styles = {
        "современн": "modern", "модерн": "modern", "минимализм": "minimalist",
        "классическ": "classical", "барокко": "baroque", "лофт": "loft",
        "скандинавск": "scandinavian", "хайтек": "hightech", "прованс": "provence",
    }
    for kw, style in styles.items():
        if kw in prompt_lower:
            result["style"] = style
            break
    
    # Features
    feature_map = {
        "балкон": "balcony", "гараж": "garage", "терраса": "terrace",
        "камин": "fireplace", "бассейн": "pool", "мансард": "mansard",
    }
    for kw, feat in feature_map.items():
        if kw in prompt_lower:
            result["features"].append(feat)
    
    return result


def _params_to_aedifex_scene(params: dict, job_id: str) -> dict:
    """
    Конвертация параметров здания → aedifex scene JSON.
    
    Создает структуру: Site → Building → Level → Walls/Doors/Windows
    """
    gen_type = params.get("gen_type", "building")
    width = params.get("width", 10)
    length = params.get("length", 12)
    floors = params.get("floors", 1)
    wall_height = params.get("wall_height", 3.0)
    wall_thickness = params.get("wall_thickness", 0.3)
    
    nodes = {}
    root_ids = []
    
    # Site
    site_id = f"site_{job_id}"
    nodes[site_id] = {
        "object": "node",
        "id": site_id,
        "type": "site",
        "name": "Site",
        "parentId": None,
        "visible": True,
        "polygon": {
            "type": "polygon",
            "points": [
                [-width, -length],
                [width, -length],
                [width, length],
                [-width, length],
            ],
        },
        "children": [],
        "metadata": {},
    }
    root_ids.append(site_id)
    
    # Building
    building_id = f"building_{job_id}"
    nodes[building_id] = {
        "object": "node",
        "id": building_id,
        "type": "building",
        "name": f"Building ({params.get('style', 'modern')})",
        "parentId": site_id,
        "visible": True,
        "position": [0, 0, 0],
        "rotation": [0, 0, 0],
        "children": [],
        "metadata": {"style": params.get("style", "modern")},
    }
    nodes[site_id]["children"].append(building_id)
    
    # Levels + Walls
    for floor_idx in range(max(1, floors)):
        level_id = f"level_{job_id}_{floor_idx}"
        elevation = floor_idx * wall_height
        
        nodes[level_id] = {
            "object": "node",
            "id": level_id,
            "type": "level",
            "name": f"Floor {floor_idx + 1}",
            "level": floor_idx,
            "parentId": building_id,
            "visible": True,
            "children": [],
            "metadata": {"elevation": elevation},
        }
        nodes[building_id]["children"].append(level_id)
        
        # 4 стены (прямоугольник)
        hw = width / 2
        hl = length / 2
        wall_defs = [
            ([[-hw, -hl], [hw, -hl]], "South Wall"),
            ([[hw, -hl], [hw, hl]], "East Wall"),
            ([[hw, hl], [-hw, hl]], "North Wall"),
            ([[-hw, hl], [-hw, -hl]], "West Wall"),
        ]
        
        for wall_idx, (pts, name) in enumerate(wall_defs):
            wall_id = f"wall_{job_id}_{floor_idx}_{wall_idx}"
            nodes[wall_id] = {
                "object": "node",
                "id": wall_id,
                "type": "wall",
                "name": name,
                "parentId": level_id,
                "visible": True,
                "start": pts[0],
                "end": pts[1],
                "thickness": wall_thickness,
                "height": wall_height,
                "frontSide": "unknown",
                "backSide": "unknown",
                "children": [],
                "metadata": {},
            }
            nodes[level_id]["children"].append(wall_id)
            
            # Окна на каждой стене (кроме если это interior)
            if gen_type != "interior" and wall_idx % 2 == 0:
                win_id = f"window_{job_id}_{floor_idx}_{wall_idx}"
                wall_len = ((pts[1][0] - pts[0][0])**2 + (pts[1][1] - pts[0][1])**2)**0.5
                nodes[win_id] = {
                    "object": "node",
                    "id": win_id,
                    "type": "window",
                    "name": f"Window {wall_idx + 1}",
                    "parentId": wall_id,
                    "visible": True,
                    "width": min(1.5, wall_len * 0.4),
                    "height": 1.2,
                    "position": [wall_len / 2, 0.9 + 1.2 / 2, 0],
                    "metadata": {},
                }
                nodes[wall_id]["children"].append(win_id)
        
        # Дверь на южной стене
        door_id = f"door_{job_id}_{floor_idx}"
        south_wall_id = f"wall_{job_id}_{floor_idx}_0"
        nodes[door_id] = {
            "object": "node",
            "id": door_id,
            "type": "door",
            "name": "Main Door",
            "parentId": south_wall_id,
            "visible": True,
            "width": 0.9,
            "height": 2.1,
            "position": [width / 2, 2.1 / 2, 0],
            "metadata": {},
        }
        nodes[south_wall_id]["children"].append(door_id)
    
    # Slab (пол) для каждого этажа
    for floor_idx in range(max(1, floors)):
        slab_id = f"slab_{job_id}_{floor_idx}"
        hw = width / 2
        hl = length / 2
        elevation = floor_idx * wall_height
        nodes[slab_id] = {
            "object": "node",
            "id": slab_id,
            "type": "slab",
            "name": f"Floor Slab {floor_idx + 1}",
            "parentId": f"level_{job_id}_{floor_idx}",
            "visible": True,
            "polygon": [[-hw, -hl], [hw, -hl], [hw, hl], [-hw, hl]],
            "holes": [],
            "elevation": elevation,
            "metadata": {},
        }
        nodes[f"level_{job_id}_{floor_idx}"]["children"].append(slab_id)
    
    return {"nodes": nodes, "rootNodeIds": root_ids}


# ═══════════════════════════════════════════════════════════════
# 2. IFC Export (aedifex scene → IFC через ifc-service)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/export/ifc")
async def export_ifc(req: ExportRequest):
    """
    Экспорт aedifex сцены в IFC формат.
    
    Использует существующий ifc-service для генерации IFC.
    """
    scene = req.scene
    
    # Конвертируем aedifex scene → параметры для ifc-service
    building_params = _aedifex_scene_to_ifc_params(scene)
    
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            # FIX: real ifc-service route is /api/v1/ifc/generate (was calling
            # the non-existent /generate-ifc, which always 404'd).
            resp = await client.post(
                f"{IFC_SERVICE_URL}/api/v1/ifc/generate",
                json={"building": building_params, "version": "IFC2X3"},
            )
            resp.raise_for_status()
            # FIX: ifc-service returns the generated .ifc file as a binary
            # FileResponse, not JSON — resp.json() raised on every successful
            # call. Pass the bytes straight through.
            return Response(
                content=resp.content,
                media_type=resp.headers.get("content-type", "application/x-step"),
                headers={
                    "Content-Disposition": resp.headers.get(
                        "content-disposition", 'attachment; filename="model.ifc"'
                    )
                },
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"IFC export failed: {e}")
            raise HTTPException(status_code=502, detail=f"ifc-service error: {e.response.text[:300]}")
        except Exception as e:
            logger.error(f"IFC export failed: {e}")
            raise HTTPException(status_code=500, detail=f"IFC export failed: {str(e)}")


def _aedifex_scene_to_ifc_params(scene: AedifexScene) -> dict:
    """Конвертация aedifex scene → параметры для ifc-service."""
    params = {
        "walls": [],
        "doors": [],
        "windows": [],
        "slabs": [],
        "levels": [],
    }
    
    for node_id, node in scene.nodes.items():
        node_type = node.get("type")
        
        if node_type == "wall":
            params["walls"].append({
                "start": node.get("start", [0, 0]),
                "end": node.get("end", [0, 0]),
                "thickness": node.get("thickness", 0.3),
                "height": node.get("height", 3.0),
            })
        elif node_type == "door":
            params["doors"].append({
                "width": node.get("width", 0.9),
                "height": node.get("height", 2.1),
                "position": node.get("position", [0, 0, 0]),
                "wall_id": node.get("parentId"),
            })
        elif node_type == "window":
            params["windows"].append({
                "width": node.get("width", 1.0),
                "height": node.get("height", 1.2),
                "position": node.get("position", [0, 0, 0]),
                "wall_id": node.get("parentId"),
            })
        elif node_type == "slab":
            params["slabs"].append({
                "polygon": node.get("polygon", []),
                "elevation": node.get("elevation", 0),
            })
        elif node_type == "level":
            params["levels"].append({
                "name": node.get("name", ""),
                "elevation": node.get("metadata", {}).get("elevation", 0),
            })
    
    return params


# ═══════════════════════════════════════════════════════════════
# 3. DXF Import (через cad-service + ezdxf)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/import/dxf")
async def import_dxf(
    file: UploadFile = File(...),
    convert_to_walls: bool = True,
    wall_height: float = 3.0,
    wall_thickness: float = 0.3,
):
    """
    Импорт DXF файла → aedifex scene.
    
    Pipeline:
    1. Читаем DXF через ezdxf (в cad-service)
    2. Конвертируем линии → стены
    3. Возвращаем aedifex scene JSON
    """
    content = await file.read()
    
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.post(
                f"{CAD_SERVICE_URL}/api/v1/cad/import-dxf",
                content=content,
                headers={"Content-Type": "application/octet-stream"},
                params={
                    "convert_to_walls": convert_to_walls,
                    "wall_height": wall_height,
                    "wall_thickness": wall_thickness,
                },
            )
            resp.raise_for_status()
            dxf_data = resp.json()
        except Exception as e:
            logger.error(f"DXF import failed: {e}")
            raise HTTPException(status_code=500, detail=f"DXF import failed: {str(e)}")
    
    # Конвертируем DXF данные → aedifex scene
    scene = _dxf_to_aedifex_scene(dxf_data, wall_height, wall_thickness)
    
    return {
        "status": "ok",
        "scene": scene,
        "entities_count": len(dxf_data.get("entities", [])),
        "message": f"Импортировано {len(dxf_data.get('entities', []))} элементов",
    }


def _dxf_to_aedifex_scene(dxf_data: dict, wall_height: float, wall_thickness: float) -> dict:
    """Конвертация DXF данных → aedifex scene."""
    nodes = {}
    root_ids = []
    
    job_id = uuid.uuid4().hex[:8]
    
    # Site
    site_id = f"site_{job_id}"
    nodes[site_id] = {
        "object": "node", "id": site_id, "type": "site", "name": "DXF Import",
        "parentId": None, "visible": True,
        "polygon": {"type": "polygon", "points": [[-50, -50], [50, -50], [50, 50], [-50, 50]]},
        "children": [], "metadata": {},
    }
    root_ids.append(site_id)
    
    # Building
    building_id = f"building_{job_id}"
    nodes[building_id] = {
        "object": "node", "id": building_id, "type": "building", "name": "Imported Building",
        "parentId": site_id, "visible": True, "position": [0, 0, 0], "rotation": [0, 0, 0],
        "children": [], "metadata": {},
    }
    nodes[site_id]["children"].append(building_id)
    
    # Level
    level_id = f"level_{job_id}_0"
    nodes[level_id] = {
        "object": "node", "id": level_id, "type": "level", "name": "Floor 1",
        "level": 0, "parentId": building_id, "visible": True,
        "children": [], "metadata": {"elevation": 0},
    }
    nodes[building_id]["children"].append(level_id)
    
    # Walls from DXF lines
    for idx, entity in enumerate(dxf_data.get("entities", [])):
        if entity.get("type") == "LINE":
            start = entity.get("start", [0, 0])
            end = entity.get("end", [0, 0])
            wall_id = f"wall_{job_id}_{idx}"
            nodes[wall_id] = {
                "object": "node", "id": wall_id, "type": "wall",
                "name": entity.get("name", f"Wall {idx + 1}"),
                "parentId": level_id, "visible": True,
                "start": start[:2], "end": end[:2],
                "thickness": wall_thickness, "height": wall_height,
                "frontSide": "unknown", "backSide": "unknown",
                "children": [], "metadata": {"dxf_layer": entity.get("layer", "0")},
            }
            nodes[level_id]["children"].append(wall_id)
    
    return {"nodes": nodes, "rootNodeIds": root_ids}


# ═══════════════════════════════════════════════════════════════
# 4. Blender Render (aedifex scene → Blender)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/render")
async def render_scene(req: RenderRequest):
    """
    Рендер aedifex сцены через Blender pipeline.
    
    Pipeline:
    1. Конвертируем aedifex scene → bpy скрипт
    2. Отправляем в Blender Service
    3. Возвращает URL рендера
    """
    scene = req.scene
    
    # Конвертируем scene → параметры для Blender
    render_params = _aedifex_scene_to_blender_params(scene, req.quality, req.resolution)
    
    async with httpx.AsyncClient(timeout=600) as client:
        try:
            resp = await client.post(
                f"{BLENDER_SERVICE_URL}/render",
                json=render_params,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Render failed: {e}")
            raise HTTPException(status_code=500, detail=f"Render failed: {str(e)}")


def _aedifex_scene_to_blender_params(scene: AedifexScene, quality: str, resolution: str) -> dict:
    """Конвертация aedifex scene → параметры для Blender Service."""
    walls = []
    windows = []
    doors = []
    
    for node_id, node in scene.nodes.items():
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
        "gen_type": "building",
        "params": {
            "walls": walls,
            "windows": windows,
            "doors": doors,
        },
        "quality": quality,
        "resolution": resolution,
    }


# ═══════════════════════════════════════════════════════════════
# 5. Parametric Wall Generation (через CadQuery)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/parametric/wall")
async def generate_parametric_wall(
    length: float = 10.0,
    height: float = 3.0,
    thickness: float = 0.3,
    windows: list[dict] | None = None,
    doors: list[dict] | None = None,
):
    """
    Генерация параметрической стены с проёмами через CadQuery.
    
    windows: [{"width": 1.2, "height": 1.5, "sill_height": 0.9, "position": 3.0}]
    doors: [{"width": 0.9, "height": 2.1, "position": 5.0}]
    """
    params = {
        "length": length,
        "height": height,
        "thickness": thickness,
        "windows": windows or [],
        "doors": doors or [],
    }
    
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.post(
                f"{CAD_SERVICE_URL}/api/v1/cad/parametric-wall",
                json=params,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Parametric wall generation failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 6. Proxy к Gateway (для обратной совместимости)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/v1/generate")
async def proxy_generate(req: GenerateFromPromptRequest):
    """Proxy к существующему Gateway — обратная совместимость."""
    async with httpx.AsyncClient(timeout=300) as client:
        try:
            resp = await client.post(
                f"{GATEWAY_URL}/api/v1/generate",
                json={"prompt": req.prompt},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Gateway error: {str(e)}")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
