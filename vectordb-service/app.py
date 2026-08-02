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
from typing import Optional, List

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


# ═══════════════════════════════════════════════════════════════
# SEMANTIC PROMPT SEARCH — for architecture reference matching
# ═══════════════════════════════════════════════════════════════

class PromptSearchRequest(BaseModel):
    prompt: str
    collection: str = "arch_references"
    limit: int = 5
    style_filter: str = ""
    type_filter: str = ""  # building|interior|landscape


class PromptIndexRequest(BaseModel):
    collection: str = "arch_references"
    items: list  # [{id, prompt, params, style, type, image_url}]


def _simple_embedding(text: str, dim: int = 128) -> list[float]:
    """
    Simple hash-based embedding for text.
    NOT semantic — just a fast fallback when no ML model is available.
    For production, replace with sentence-transformers or OpenAI embeddings.
    """
    import hashlib
    import struct

    # Normalize
    text = text.lower().strip()
    words = text.split()

    # Create multiple hashes and combine
    vec = [0.0] * dim
    for i, word in enumerate(words[:32]):  # max 32 words
        h = hashlib.sha256(f"{word}_{i}".encode()).digest()
        for j in range(min(dim, len(h) // 4)):
            val = struct.unpack_from('f', h, j * 4)[0]
            if -100 < val < 100:  # sanity check
                vec[j % dim] += val

    # Normalize
    magnitude = sum(v * v for v in vec) ** 0.5
    if magnitude > 0:
        vec = [v / magnitude for v in vec]

    return vec


@app.post("/api/v1/vectordb/search_by_prompt")
async def search_by_prompt(req: PromptSearchRequest):
    """
    Search for similar architectural prompts.
    Enables RAG: find similar past projects for context.
    """
    # Generate embedding from prompt
    vector = _simple_embedding(req.prompt)

    # Build filter
    search_filter = {}
    must_conditions = []
    if req.style_filter:
        must_conditions.append({"key": "style", "match": {"value": req.style_filter}})
    if req.type_filter:
        must_conditions.append({"key": "type", "match": {"value": req.type_filter}})
    if must_conditions:
        search_filter["must"] = must_conditions

    search_data = {
        "vector": vector,
        "limit": req.limit,
        "with_payload": True,
    }
    if search_filter:
        search_data["filter"] = search_filter

    try:
        result = await qdrant_request(
            "POST",
            f"/collections/{req.collection}/points/search",
            search_data,
        )
        hits = result.get("result", [])
        return {
            "query": req.prompt,
            "results": [
                {
                    "id": h.get("id"),
                    "score": h.get("score", 0),
                    "params": h.get("payload", {}).get("params", {}),
                    "style": h.get("payload", {}).get("style", ""),
                    "type": h.get("payload", {}).get("type", ""),
                    "prompt": h.get("payload", {}).get("prompt", ""),
                    "image_url": h.get("payload", {}).get("image_url", ""),
                }
                for h in hits
            ],
        }
    except Exception as e:
        # Collection might not exist yet
        return {"query": req.prompt, "results": [], "error": str(e)}


@app.post("/api/v1/vectordb/index_prompts")
async def index_prompts(req: PromptIndexRequest):
    """
    Index architectural prompts for semantic search.
    Call after successful generation to build reference library.
    """
    points = []
    for item in req.items:
        prompt_text = item.get("prompt", "")
        vector = _simple_embedding(prompt_text)
        points.append({
            "id": item.get("id", str(hash(prompt_text))[:8]),
            "vector": vector,
            "payload": {
                "prompt": prompt_text,
                "params": item.get("params", {}),
                "style": item.get("style", ""),
                "type": item.get("type", ""),
                "image_url": item.get("image_url", ""),
            },
        })

    try:
        # Ensure collection exists
        await qdrant_request("PUT", f"/collections/{req.collection}", {
            "vectors": {"size": 128, "distance": "Cosine"}
        })
    except Exception:
        pass  # Collection might already exist

    return await qdrant_request("PUT", f"/collections/{req.collection}/points", {
        "points": points,
    })


if __name__ == "__main__":
    import uvicorn
    print(f"Vector DB Service starting on port {PORT}")
    print(f"Qdrant URL: {QDRANT_URL}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
