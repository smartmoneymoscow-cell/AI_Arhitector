"""
Vector DB Service — Qdrant wrapper for vector search

Wraps Qdrant HTTP API for:
  - Collection management
  - Vector insert/upsert
  - Similarity search
  - Filtering

Dependencies: httpx (qdrant runs as separate Docker container)
"""
import os
import uuid
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Architect Vector DB Service",
    description="Qdrant wrapper for vector search",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PORT = int(os.environ.get("PORT", 8089))
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")

# ═══════════════════════════════════════════════════════════════
# QDRANT CLIENT
# ═══════════════════════════════════════════════════════════════

import httpx


async def qdrant_request(method: str, path: str, data: dict = None) -> dict:
    """Make request to Qdrant HTTP API."""
    async with httpx.AsyncClient() as client:
        try:
            url = f"{QDRANT_URL}{path}"
            if method == "GET":
                r = await client.get(url, timeout=10.0)
            elif method == "POST":
                r = await client.post(url, json=data, timeout=10.0)
            elif method == "PUT":
                r = await client.put(url, json=data, timeout=10.0)
            elif method == "DELETE":
                r = await client.delete(url, timeout=10.0)
            else:
                raise ValueError(f"Unknown method: {method}")

            if r.status_code >= 400:
                raise HTTPException(r.status_code, r.text)
            return r.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Qdrant not available. Start with: docker run -p 6333:6333 qdrant/qdrant")


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    try:
        result = await qdrant_request("GET", "/")
        qdrant_ok = True
        version = result.get("version", "unknown")
    except:
        qdrant_ok = False
        version = "unavailable"

    return {
        "status": "ok",
        "service": "vectordb-service",
        "qdrant_available": qdrant_ok,
        "qdrant_version": version,
    }


class CollectionCreate(BaseModel):
    name: str
    vector_size: int = 128
    distance: str = "Cosine"  # "Cosine", "Euclid", "Dot"


@app.post("/api/v1/vectordb/collections")
async def create_collection(req: CollectionCreate):
    """Create a new collection."""
    return await qdrant_request("PUT", f"/collections/{req.name}", {
        "vectors": {
            "size": req.vector_size,
            "distance": req.distance,
        }
    })


@app.get("/api/v1/vectordb/collections")
async def list_collections():
    """List all collections."""
    return await qdrant_request("GET", "/collections")


@app.get("/api/v1/vectordb/collections/{name}")
async def get_collection(name: str):
    """Get collection info."""
    return await qdrant_request("GET", f"/collections/{name}")


@app.delete("/api/v1/vectordb/collections/{name}")
async def delete_collection(name: str):
    """Delete collection."""
    return await qdrant_request("DELETE", f"/collections/{name}")


class Point(BaseModel):
    id: str
    vector: List[float]
    payload: dict = {}


class UpsertRequest(BaseModel):
    collection: str
    points: List[Point]


@app.post("/api/v1/vectordb/upsert")
async def upsert_points(req: UpsertRequest):
    """Insert or update vectors."""
    points = [
        {"id": p.id, "vector": p.vector, "payload": p.payload}
        for p in req.points
    ]
    return await qdrant_request("PUT", f"/collections/{req.collection}/points", {
        "points": points,
    })


class SearchRequest(BaseModel):
    collection: str
    vector: List[float]
    limit: int = 10
    score_threshold: float = 0.0
    filter: dict = {}


@app.post("/api/v1/vectordb/search")
async def search_vectors(req: SearchRequest):
    """Search for similar vectors."""
    data = {
        "vector": req.vector,
        "limit": req.limit,
        "score_threshold": req.score_threshold,
    }
    if req.filter:
        data["filter"] = req.filter

    return await qdrant_request("POST", f"/collections/{req.collection}/points/search", data)


class ScrollRequest(BaseModel):
    collection: str
    limit: int = 10
    offset: Optional[str] = None
    filter: dict = {}


@app.post("/api/v1/vectordb/scroll")
async def scroll_points(req: ScrollRequest):
    """Scroll through points in collection."""
    params = {"limit": req.limit}
    if req.offset:
        params["offset"] = req.offset
    if req.filter:
        params["filter"] = req.filter

    return await qdrant_request("POST", f"/collections/{req.collection}/points/scroll", params)


if __name__ == "__main__":
    import uvicorn
    print(f"Vector DB Service starting on port {PORT}")
    print(f"Qdrant URL: {QDRANT_URL}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
