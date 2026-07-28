"""
Graph DB Service — Neo4j wrapper for knowledge graphs

Wraps Neo4j HTTP API for:
  - BIM element relationships
  - Spatial connectivity graphs
  - Building knowledge graph queries
  - Path finding

Dependencies: httpx (neo4j runs as separate Docker container)
"""
import os
import json
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Architect Graph DB Service",
    description="Neo4j wrapper for BIM knowledge graphs",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PORT = int(os.environ.get("PORT", 8090))
NEO4J_URL = os.environ.get("NEO4J_URL", "http://localhost:7474")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

# ═══════════════════════════════════════════════════════════════
# NEO4J CLIENT
# ═══════════════════════════════════════════════════════════════

import httpx


async def neo4j_cypher(query: str, params: dict = None) -> dict:
    """Execute a Cypher query on Neo4j."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{NEO4J_URL}/db/neo4j/tx/commit",
                auth=(NEO4J_USER, NEO4J_PASSWORD),
                json={
                    "statements": [{
                        "statement": query,
                        "parameters": params or {},
                    }]
                },
                timeout=30.0,
            )
            if r.status_code >= 400:
                raise HTTPException(r.status_code, r.text)
            return r.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Neo4j not available. Start with: docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j")


# ═══════════════════════════════════════════════════════════════
# BIM KNOWLEDGE GRAPH OPERATIONS
# ═══════════════════════════════════════════════════════════════

async def create_building_graph(building: dict) -> dict:
    """Create a knowledge graph from building data."""
    queries = []

    # Create building node
    bid = building.get("id", "building")
    queries.append((
        "MERGE (b:Building {id: $id}) SET b.name = $name, b.type = $type",
        {"id": bid, "name": building.get("name", "Building"),
         "type": building.get("building_type", "house")}
    ))

    # Create floors and rooms
    for floor_data in building.get("floors", []):
        fid = f"{bid}_floor_{floor_data.get('level', 0)}"
        queries.append((
            "MERGE (f:Floor {id: $id}) SET f.level = $level "
            "WITH f MATCH (b:Building {id: $bid}) MERGE (b)-[:HAS_FLOOR]->(f)",
            {"id": fid, "level": floor_data.get("level", 0), "bid": bid}
        ))

        for room in floor_data.get("rooms", []):
            rid = room.get("id", f"{fid}_room_{len(queries)}")
            queries.append((
                "MERGE (r:Room {id: $id}) SET r.name = $name, r.type = $type, r.area = $area "
                "WITH r MATCH (f:Floor {id: $fid}) MERGE (f)-[:HAS_ROOM]->(r)",
                {"id": rid, "name": room.get("name", "Room"),
                 "type": room.get("room_type", "unknown"),
                 "area": room.get("area", 0), "fid": fid}
            ))

            # Create wall nodes
            for wall in room.get("walls", []):
                wid = wall.get("id", f"{rid}_wall")
                queries.append((
                    "MERGE (w:Wall {id: $id}) SET w.material = $mat, w.thickness = $t "
                    "WITH w MATCH (r:Room {id: $rid}) MERGE (r)-[:HAS_WALL]->(w)",
                    {"id": wid, "mat": wall.get("material", "brick"),
                     "t": wall.get("thickness", 0.3), "rid": rid}
                ))

    # Execute all queries
    results = []
    for query, params in queries:
        result = await neo4j_cypher(query, params)
        results.append(result)

    return {
        "nodes_created": len(queries),
        "status": "ok",
    }


async def find_room_connections(building_id: str) -> dict:
    """Find room adjacency graph."""
    result = await neo4j_cypher(
        "MATCH (b:Building {id: $bid})-[:HAS_FLOOR]->(f)-[:HAS_ROOM]->(r) "
        "OPTIONAL MATCH (r)-[:CONNECTS_TO]->(connected) "
        "RETURN r.id, r.name, r.type, collect(connected.name) as connections",
        {"bid": building_id}
    )
    return result


async def find_shortest_path(from_room: str, to_room: str) -> dict:
    """Find shortest path between two rooms."""
    result = await neo4j_cypher(
        "MATCH path = shortestPath("
        "(a:Room {name: $from})-[:CONNECTS_TO*]-(b:Room {name: $to}))"
        "RETURN [n IN nodes(path) | n.name] as path, length(path) as hops",
        {"from": from_room, "to": to_room}
    )
    return result


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    neo4j_ok = False
    version = "unavailable"
    try:
        result = await neo4j_cypher("RETURN 1 as n")
        neo4j_ok = True
        version = "connected"
    except:
        pass

    return {
        "status": "ok",
        "service": "graphdb-service",
        "neo4j_available": neo4j_ok,
    }


class CypherRequest(BaseModel):
    query: str
    params: dict = {}


@app.post("/api/v1/graph/cypher")
async def execute_cypher(req: CypherRequest):
    """Execute a Cypher query."""
    return await neo4j_cypher(req.query, req.params)


class BuildingGraphRequest(BaseModel):
    building: dict


@app.post("/api/v1/graph/building")
async def create_graph(req: BuildingGraphRequest):
    """Create building knowledge graph."""
    return await create_building_graph(req.building)


class PathRequest(BaseModel):
    from_room: str
    to_room: str


@app.post("/api/v1/graph/path")
async def graph_path(req: PathRequest):
    """Find shortest path between rooms in graph."""
    return await find_shortest_path(req.from_room, req.to_room)


@app.get("/api/v1/graph/building/{building_id}/rooms")
async def building_rooms(building_id: str):
    """Get all rooms in a building graph."""
    return await find_room_connections(building_id)


if __name__ == "__main__":
    import uvicorn
    print(f"Graph DB Service starting on port {PORT}")
    print(f"Neo4j URL: {NEO4J_URL}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
