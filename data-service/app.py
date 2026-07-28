"""
Data Service — Storage and vector search for BIM data

Capabilities:
  - SQLite storage for projects and buildings (lightweight)
  - Vector embeddings for semantic search (numpy-based, Qdrant optional)
  - Project CRUD operations
  - Search by description, style, type

Dependencies: numpy (Qdrant optional)
"""
import os
import json
import uuid
import time
from typing import Optional, List, Dict, Any

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Architect Data Service",
    description="BIM data storage and vector search",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PORT = int(os.environ.get("PORT", 8086))
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
os.makedirs(DATA_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# SIMPLE FILE-BASED STORAGE (no external DB needed)
# ═══════════════════════════════════════════════════════════════

PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
EMBEDDINGS_FILE = os.path.join(DATA_DIR, "embeddings.npz")


def _load_projects() -> dict:
    if os.path.exists(PROJECTS_FILE):
        with open(PROJECTS_FILE) as f:
            return json.load(f)
    return {}


def _save_projects(projects: dict):
    with open(PROJECTS_FILE, "w") as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# VECTOR EMBEDDINGS (simple TF-IDF-like, no heavy deps)
# ═══════════════════════════════════════════════════════════════

VOCAB = {}  # word -> index
IDF = {}    # word -> idf score
DIM = 128   # embedding dimension


def _tokenize(text: str) -> List[str]:
    """Simple tokenization."""
    import re
    text = text.lower()
    tokens = re.findall(r'[а-яёa-z0-9]+', text)
    return tokens


def _build_embedding(text: str) -> np.ndarray:
    """Build simple TF-IDF-like embedding."""
    tokens = _tokenize(text)
    if not tokens:
        return np.zeros(DIM)

    # Term frequency
    tf = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    max_tf = max(tf.values())
    tf = {k: v / max_tf for k, v in tf.items()}

    # Create embedding vector
    vec = np.zeros(DIM)
    for word, freq in tf.items():
        # Hash word to dimension
        idx = hash(word) % DIM
        idf = IDF.get(word, 1.0)
        vec[idx] += freq * idf

    # Normalize
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm

    return vec


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    projects = _load_projects()
    return {
        "status": "ok",
        "service": "data-service",
        "projects": len(projects),
    }


# ── PROJECT CRUD ─────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    building: dict = {}
    tags: List[str] = []


@app.post("/api/v1/projects")
async def create_project(req: ProjectCreate):
    """Create a new project."""
    projects = _load_projects()
    pid = uuid.uuid4().hex[:12]

    project = {
        "id": pid,
        "name": req.name,
        "description": req.description,
        "building": req.building,
        "tags": req.tags,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    projects[pid] = project
    _save_projects(projects)

    # Store embedding
    embedding = _build_embedding(f"{req.name} {req.description} {' '.join(req.tags)}")
    _save_embedding(pid, embedding)

    return project


@app.get("/api/v1/projects/{project_id}")
async def get_project(project_id: str):
    """Get project by ID."""
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(404, "Project not found")
    return projects[project_id]


@app.get("/api/v1/projects")
async def list_projects(limit: int = 50, offset: int = 0):
    """List all projects."""
    projects = _load_projects()
    items = list(projects.values())
    items.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
    return {
        "total": len(items),
        "items": items[offset:offset+limit],
    }


@app.put("/api/v1/projects/{project_id}")
async def update_project(project_id: str, req: ProjectCreate):
    """Update project."""
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(404, "Project not found")

    projects[project_id].update({
        "name": req.name,
        "description": req.description,
        "building": req.building,
        "tags": req.tags,
        "updated_at": time.time(),
    })
    _save_projects(projects)

    # Update embedding
    embedding = _build_embedding(f"{req.name} {req.description} {' '.join(req.tags)}")
    _save_embedding(project_id, embedding)

    return projects[project_id]


@app.delete("/api/v1/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete project."""
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(404, "Project not found")
    del projects[project_id]
    _save_projects(projects)
    return {"deleted": project_id}


# ── VECTOR SEARCH ────────────────────────────────────────────

def _save_embedding(project_id: str, embedding: np.ndarray):
    """Save project embedding."""
    try:
        if os.path.exists(EMBEDDINGS_FILE):
            data = np.load(EMBEDDINGS_FILE, allow_pickle=True)
            ids = list(data["ids"]) if "ids" in data else []
            vecs = list(data["vecs"]) if "vecs" in data else []
        else:
            ids = []
            vecs = []

        # Update or add
        if project_id in ids:
            idx = ids.index(project_id)
            vecs[idx] = embedding
        else:
            ids.append(project_id)
            vecs.append(embedding)

        np.savez(EMBEDDINGS_FILE,
                 ids=np.array(ids),
                 vecs=np.array(vecs))
    except Exception as e:
        print(f"[data-service] Embedding save error: {e}")


def _search_embeddings(query_embedding: np.ndarray, top_k: int = 5) -> List[dict]:
    """Search for similar projects."""
    if not os.path.exists(EMBEDDINGS_FILE):
        return []

    data = np.load(EMBEDDINGS_FILE, allow_pickle=True)
    ids = data["ids"]
    vecs = data["vecs"]

    if len(ids) == 0:
        return []

    # Compute similarities
    similarities = []
    for i, pid in enumerate(ids):
        sim = _cosine_similarity(query_embedding, vecs[i])
        similarities.append({"project_id": str(pid), "score": round(sim, 3)})

    # Sort by similarity
    similarities.sort(key=lambda x: x["score"], reverse=True)
    return similarities[:top_k]


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


@app.post("/api/v1/search")
async def search_projects(req: SearchRequest):
    """Semantic search for projects."""
    query_embedding = _build_embedding(req.query)
    results = _search_embeddings(query_embedding, req.top_k)

    # Enrich with project data
    projects = _load_projects()
    enriched = []
    for r in results:
        pid = r["project_id"]
        if pid in projects:
            enriched.append({
                **r,
                "name": projects[pid].get("name", ""),
                "description": projects[pid].get("description", ""),
                "tags": projects[pid].get("tags", []),
            })

    return {"query": req.query, "results": enriched}


# ── TEMPLATES ────────────────────────────────────────────────

@app.get("/api/v1/templates")
async def list_templates():
    """List building templates."""
    templates = [
        {
            "id": "house-2floor",
            "name": "Жилой дом 2 этажа",
            "building_type": "house",
            "floors": 2,
            "width_m": 10, "length_m": 12,
            "style": "modern",
            "description": "Стандартный жилой дом для семьи",
        },
        {
            "id": "cottage-wood",
            "name": "Деревянный коттедж",
            "building_type": "cottage",
            "floors": 2,
            "width_m": 12, "length_m": 15,
            "style": "scandinavian",
            "material": "wood",
            "description": "Уютный коттедж из дерева",
        },
        {
            "id": "office-5floor",
            "name": "Офисное здание",
            "building_type": "office",
            "floors": 5,
            "width_m": 20, "length_m": 30,
            "style": "hitech",
            "material": "glass",
            "description": "Современный офисный центр",
        },
        {
            "id": "apartment-modern",
            "name": "Квартира-студия",
            "building_type": "apartment",
            "floors": 1,
            "width_m": 8, "length_m": 10,
            "style": "minimalist",
            "description": "Современная квартира-студия",
        },
    ]
    return {"templates": templates}


if __name__ == "__main__":
    import uvicorn
    print(f"Data Service starting on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
