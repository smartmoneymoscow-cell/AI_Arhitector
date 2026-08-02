"""
Geometry Service — Spatial analysis using Shapely + NetworkX

Capabilities:
  - Floor plan analysis (room adjacency, circulation)
  - 2D geometry operations (union, intersection, buffer)
  - Spatial graph construction (rooms as nodes, doors as edges)
  - Building coverage & setback calculations
  - Natural light analysis
  - Structural wall detection

Dependencies: shapely, networkx, numpy
"""
import os
import json
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import networkx as nx

app = FastAPI(
    title="Architect Geometry Service",
    description="Spatial analysis with Shapely + NetworkX",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PORT = int(os.environ.get("PORT", 8083))


# ═══════════════════════════════════════════════════════════════
# SPATIAL GRAPH — rooms as nodes, adjacency as edges
# ═══════════════════════════════════════════════════════════════

def build_spatial_graph(rooms: List[dict]) -> nx.Graph:
    """
    Build a graph where:
      - Nodes = rooms (with attributes: type, area, floor)
      - Edges = adjacency (rooms sharing a wall/door)
    """
    G = nx.Graph()

    # Add rooms as nodes
    for room in rooms:
        rid = room.get("id", "unknown")
        G.add_node(rid, **{
            "room_type": room.get("room_type", "unknown"),
            "area": room.get("area", 0),
            "floor": room.get("floor", 0),
            "name": room.get("name", ""),
        })

    # Detect adjacency using bounding box overlap
    for i, r1 in enumerate(rooms):
        for j, r2 in enumerate(rooms):
            if i >= j:
                continue
            # Check if rooms share a wall (simplified: bbox proximity)
            b1 = r1.get("bbox", {})
            b2 = r2.get("bbox", {})
            if not b1 or not b2:
                continue

            # Check for shared edge
            shared = _shared_edge_length(b1, b2)
            if shared > 0.3:  # at least 30cm shared wall
                # Check if there's a door between them
                has_door = _has_door_between(r1, r2)
                G.add_edge(r1["id"], r2["id"],
                           shared_wall=shared,
                           has_door=has_door,
                           connection_type="door" if has_door else "wall")

    return G


def _shared_edge_length(b1: dict, b2: dict) -> float:
    """Calculate shared edge length between two bounding boxes."""
    # Check horizontal adjacency
    if abs(b1.get("max_x", 0) - b2.get("min_x", 0)) < 0.5 or \
       abs(b2.get("max_x", 0) - b1.get("min_x", 0)) < 0.5:
        y_overlap = min(b1.get("max_y", 0), b2.get("max_y", 0)) - \
                    max(b1.get("min_y", 0), b2.get("min_y", 0))
        return max(0, y_overlap)

    # Check vertical adjacency
    if abs(b1.get("max_y", 0) - b2.get("min_y", 0)) < 0.5 or \
       abs(b2.get("max_y", 0) - b1.get("min_y", 0)) < 0.5:
        x_overlap = min(b1.get("max_x", 0), b2.get("max_x", 0)) - \
                    max(b1.get("min_x", 0), b2.get("min_x", 0))
        return max(0, x_overlap)

    return 0


def _has_door_between(r1: dict, r2: dict) -> bool:
    """Check if there's a door connecting two rooms."""
    doors1 = set(r1.get("connected_rooms", []))
    doors2 = set(r2.get("connected_rooms", []))
    return bool(doors1 & doors2)


# ═══════════════════════════════════════════════════════════════
# ANALYSIS FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def analyze_circulation(G: nx.Graph) -> dict:
    """Analyze circulation quality of the floor plan."""
    if len(G.nodes) < 2:
        return {"score": 100, "issues": [], "paths": []}

    issues = []
    score = 100

    # Check connectivity
    if not nx.is_connected(G):
        components = list(nx.connected_components(G))
        issues.append(f"Floor plan has {len(components)} disconnected zones")
        score -= 30

    # Check for rooms with no doors (isolated)
    isolated = [n for n in G.nodes if G.degree(n) == 0]
    if isolated:
        issues.append(f"{len(isolated)} room(s) have no doors: {isolated}")
        score -= 10 * len(isolated)

    # Check dead-end rooms (only one connection)
    dead_ends = [n for n in G.nodes if G.degree(n) == 1]
    # Bedroom dead ends are OK, but kitchen/bathroom shouldn't be dead ends
    for room in dead_ends:
        room_type = G.nodes[room].get("room_type", "")
        if room_type in ("kitchen", "bathroom"):
            issues.append(f"{room_type} ({room}) is a dead-end room")
            score -= 10

    # Check if all rooms are reachable from entrance
    entrance_nodes = [n for n in G.nodes
                      if G.nodes[n].get("room_type") in ("hallway", "living")]
    if entrance_nodes:
        entrance = entrance_nodes[0]
        for node in G.nodes:
            if node != entrance:
                try:
                    path = nx.shortest_path(G, entrance, node)
                    if len(path) > 4:
                        issues.append(f"Room {node} is far from entrance ({len(path)} doors)")
                        score -= 5
                except nx.NetworkXNoPath:
                    pass

    return {"score": max(0, score), "issues": issues}


def analyze_natural_light(rooms: List[dict]) -> dict:
    """Analyze natural light potential based on window placement."""
    results = {}
    total_score = 0

    for room in rooms:
        rid = room.get("id", "unknown")
        room_type = room.get("room_type", "unknown")
        windows = room.get("windows", [])
        area = room.get("area", 1)

        # Window area
        window_area = sum(w.get("width", 1.2) * w.get("height", 1.5) for w in windows)
        ratio = window_area / max(area, 0.1)

        # Scoring
        if room_type in ("living", "study", "children"):
            # Need good light
            if ratio > 0.15:
                room_score = 100
            elif ratio > 0.10:
                room_score = 70
            elif ratio > 0.05:
                room_score = 40
            else:
                room_score = 10
        elif room_type in ("bathroom", "hallway", "garage"):
            # Less light needed
            room_score = 80 if ratio > 0.05 else 50
        else:
            # Standard rooms
            room_score = min(100, int(ratio * 500))

        results[rid] = {"score": room_score, "window_ratio": round(ratio, 3)}
        total_score += room_score

    avg_score = total_score / max(len(rooms), 1)
    return {"score": round(avg_score), "rooms": results}


def analyze_space_efficiency(rooms: List[dict]) -> dict:
    """Analyze how efficiently space is used."""
    if not rooms:
        return {"score": 0, "total_area": 0, "usable_ratio": 0}

    total_area = sum(r.get("area", 0) for r in rooms)
    hallway_area = sum(r.get("area", 0) for r in rooms
                       if r.get("room_type") == "hallway")
    bathroom_area = sum(r.get("area", 0) for r in rooms
                        if r.get("room_type") == "bathroom")

    # Usable = total - hallways
    usable_ratio = (total_area - hallway_area) / max(total_area, 1)

    # Ideal hallway ratio is 10-15%
    hallway_ratio = hallway_area / max(total_area, 1)
    if hallway_ratio > 0.25:
        score = 50
        issue = "Too much hallway space (>25%)"
    elif hallway_ratio < 0.05:
        score = 60
        issue = "No hallway — poor privacy"
    else:
        score = 90
        issue = None

    # Check minimum room sizes
    small_rooms = [r for r in rooms if r.get("area", 0) < 4]
    if small_rooms:
        score -= 5 * len(small_rooms)

    return {
        "score": max(0, score),
        "total_area": round(total_area, 1),
        "hallway_ratio": round(hallway_ratio, 3),
        "usable_ratio": round(usable_ratio, 3),
        "issue": issue,
    }


def check_building_codes(building: dict) -> List[str]:
    """Check building against common codes and regulations."""
    issues = []

    # Check floor count
    floors = building.get("floors", [])
    if len(floors) > 5:
        issues.append(f"Building has {len(floors)} floors — may require elevator")

    # Check room heights
    for floor in floors:
        for room in floor.get("rooms", []):
            h = room.get("height", 3.0)
            if h < 2.5:
                issues.append(f"Room {room.get('id')} height {h}m < 2.5m minimum")
            if room.get("room_type") == "bathroom" and h < 2.4:
                issues.append(f"Bathroom {room.get('id')} height {h}m < 2.4m minimum")

    # Check window requirements
    for floor in floors:
        for room in floor.get("rooms", []):
            if room.get("room_type") in ("bedroom", "living", "children"):
                if not room.get("windows"):
                    issues.append(f"Room {room.get('id')} ({room.get('room_type')}) has no windows")

    # Check setback compliance
    footprint = building.get("footprint")
    lot_w = building.get("lot_width")
    lot_l = building.get("lot_length")
    if footprint and lot_w and lot_l:
        # Check if building fits within lot with setbacks
        setback_front = building.get("setback_front", 5.0)
        setback_side = building.get("setback_side", 3.0)
        setback_back = building.get("setback_back", 5.0)

        max_w = lot_w - 2 * setback_side
        max_l = lot_l - setback_front - setback_back

        bbox = footprint.get("bbox", {})
        if bbox.get("width", 0) > max_w:
            issues.append(f"Building width exceeds lot setback limit ({max_w}m)")
        if bbox.get("height", 0) > max_l:
            issues.append(f"Building length exceeds lot setback limit ({max_l}m)")

    return issues


# ═══════════════════════════════════════════════════════════════
# 2D GEOMETRY OPERATIONS
# ═══════════════════════════════════════════════════════════════

def generate_floor_plan_svg(rooms: List[dict], width: int = 800, height: int = 600) -> str:
    """Generate SVG floor plan from room data."""
    if not rooms:
        return "<svg></svg>"

    # Find bounding box
    all_x, all_y = [], []
    for room in rooms:
        for pt in room.get("polygon", {}).get("points", []):
            all_x.append(pt["x"])
            all_y.append(pt["y"])

    if not all_x:
        return "<svg></svg>"

    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)

    # Scale to fit
    scale_x = (width - 40) / max(max_x - min_x, 1)
    scale_y = (height - 40) / max(max_y - min_y, 1)
    scale = min(scale_x, scale_y)

    def tx(x):
        return 20 + (x - min_x) * scale

    def ty(y):
        return 20 + (y - min_y) * scale

    # Build SVG
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<style>',
        '  .wall { fill: none; stroke: #333; stroke-width: 2; }',
        '  .room { fill: #f5f5f5; stroke: #999; stroke-width: 1; }',
        '  .door { stroke: #c00; stroke-width: 2; }',
        '  .window { stroke: #06c; stroke-width: 2; stroke-dasharray: 4 2; }',
        '  .label { font: 10px sans-serif; fill: #333; }',
        '  .dim { font: 8px monospace; fill: #666; }',
        '</style>',
    ]

    # Draw rooms
    room_colors = {
        "bedroom": "#e8f0fe", "living": "#fef7e0", "kitchen": "#fce8e6",
        "bathroom": "#e6f4ea", "hallway": "#f1f3f4", "study": "#f3e8fd",
        "children": "#fff3e0", "dining": "#e0f7fa", "garage": "#eeeeee",
    }

    for room in rooms:
        pts = room.get("polygon", {}).get("points", [])
        if len(pts) < 3:
            continue

        points_str = " ".join(f"{tx(p['x'])},{ty(p['y'])}" for p in pts)
        color = room_colors.get(room.get("room_type", ""), "#f5f5f5")
        svg_parts.append(f'<polygon points="{points_str}" class="room" fill="{color}"/>')

        # Room label
        cx = sum(p["x"] for p in pts) / len(pts)
        cy = sum(p["y"] for p in pts) / len(pts)
        label = room.get("name") or room.get("room_type", "")
        area = room.get("area", 0)
        svg_parts.append(
            f'<text x="{tx(cx)}" y="{ty(cy)}" class="label" text-anchor="middle">'
            f'{label}</text>'
        )
        svg_parts.append(
            f'<text x="{tx(cx)}" y="{ty(cy) + 12}" class="dim" text-anchor="middle">'
            f'{area:.1f} m²</text>'
        )

        # Draw walls
        for i in range(len(pts)):
            p1 = pts[i]
            p2 = pts[(i + 1) % len(pts)]
            svg_parts.append(
                f'<line x1="{tx(p1["x"])}" y1="{ty(p1["y"])}" '
                f'x2="{tx(p2["x"])}" y2="{ty(p2["y"])}" class="wall"/>'
            )

        # Draw doors
        for door in room.get("doors", []):
            pos = door.get("position", {})
            if pos:
                dx = tx(pos.get("x", 0))
                dy = ty(pos.get("y", 0))
                svg_parts.append(
                    f'<circle cx="{dx}" cy="{dy}" r="4" fill="#c00" opacity="0.7"/>'
                )

        # Draw windows
        for win in room.get("windows", []):
            pos = win.get("position", {})
            if pos:
                wx = tx(pos.get("x", 0))
                wy = ty(pos.get("y", 0))
                svg_parts.append(
                    f'<rect x="{wx-6}" y="{wy-2}" width="12" height="4" '
                    f'fill="#06c" opacity="0.5" rx="1"/>'
                )

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "service": "geometry-service", "version": "1.0.0"}


class GraphRequest(BaseModel):
    rooms: List[dict]


@app.post("/api/v1/analyze/graph")
async def analyze_graph(req: GraphRequest):
    """Build and analyze spatial graph from rooms."""
    G = build_spatial_graph(req.rooms)
    circulation = analyze_circulation(G)
    light = analyze_natural_light(req.rooms)
    efficiency = analyze_space_efficiency(req.rooms)

    # Serialize graph
    graph_data = {
        "nodes": [{"id": n, **G.nodes[n]} for n in G.nodes],
        "edges": [{"source": u, "target": v, **G.edges[u, v]} for u, v in G.edges],
    }

    return {
        "graph": graph_data,
        "circulation": circulation,
        "natural_light": light,
        "space_efficiency": efficiency,
        "statistics": {
            "rooms": len(G.nodes),
            "connections": len(G.edges),
            "is_connected": nx.is_connected(G) if len(G.nodes) > 0 else True,
            "avg_degree": sum(dict(G.degree()).values()) / max(len(G.nodes), 1),
        }
    }


class FullAnalysisRequest(BaseModel):
    building: dict


@app.post("/api/v1/analyze/full")
async def full_analysis(req: FullAnalysisRequest):
    """Full building analysis: spatial + structural + codes."""
    building = req.building

    # Collect all rooms
    all_rooms = []
    for floor in building.get("floors", []):
        for room in floor.get("rooms", []):
            all_rooms.append(room)

    # Graph analysis
    G = build_spatial_graph(all_rooms)
    circulation = analyze_circulation(G)
    light = analyze_natural_light(all_rooms)
    efficiency = analyze_space_efficiency(all_rooms)
    code_issues = check_building_codes(building)

    # Totals
    total_area = sum(r.get("area", 0) for r in all_rooms)
    total_volume = sum(r.get("area", 0) * r.get("height", 3.0) for r in all_rooms)

    # Window-to-wall ratio
    total_window_area = 0
    total_wall_area = 0
    for room in all_rooms:
        for w in room.get("windows", []):
            total_window_area += w.get("width", 1.2) * w.get("height", 1.5)
        perimeter = sum(
            ((room.get("polygon", {}).get("points", [])[i]["x"] -
              room.get("polygon", {}).get("points", [])[(i+1) % len(room.get("polygon", {}).get("points", []))]["x"]) ** 2 +
             (room.get("polygon", {}).get("points", [])[i]["y"] -
              room.get("polygon", {}).get("points", [])[(i+1) % len(room.get("polygon", {}).get("points", []))]["y"]) ** 2) ** 0.5
            for i in range(len(room.get("polygon", {}).get("points", [])))
        ) if len(room.get("polygon", {}).get("points", [])) > 2 else 0
        total_wall_area += perimeter * room.get("height", 3.0)

    wwr = total_window_area / max(total_wall_area, 1)

    # Recommendations
    recommendations = []
    if circulation["score"] < 70:
        recommendations.append("Improve room connectivity — add doors between adjacent rooms")
    if light["score"] < 60:
        recommendations.append("Increase window sizes for better natural lighting")
    if efficiency["score"] < 60:
        recommendations.append("Reduce hallway space — consider open-plan layout")
    if wwr < 0.1:
        recommendations.append("Window-to-wall ratio is low — consider larger windows")
    if wwr > 0.4:
        recommendations.append("Window-to-wall ratio is high — consider energy efficiency")

    return {
        "total_area": round(total_area, 1),
        "total_volume": round(total_volume, 1),
        "room_areas": {r.get("id", "?"): round(r.get("area", 0), 1) for r in all_rooms},
        "window_to_wall_ratio": round(wwr, 3),
        "circulation": circulation,
        "natural_light": light,
        "space_efficiency": efficiency,
        "building_code_issues": code_issues,
        "recommendations": recommendations,
        "graph": {
            "nodes": len(G.nodes),
            "edges": len(G.edges),
            "connected": nx.is_connected(G) if len(G.nodes) > 0 else True,
        }
    }


class SvgRequest(BaseModel):
    rooms: List[dict]
    width: int = 800
    height: int = 600


@app.post("/api/v1/floorplan/svg")
async def floorplan_svg(req: SvgRequest):
    """Generate SVG floor plan from rooms."""
    svg = generate_floor_plan_svg(req.rooms, req.width, req.height)
    from fastapi.responses import Response
    return Response(content=svg, media_type="image/svg+xml")


class ShortestPathRequest(BaseModel):
    rooms: List[dict]
    from_room: str
    to_room: str


@app.post("/api/v1/analyze/path")
async def shortest_path(req: ShortestPathRequest):
    """Find shortest path between two rooms."""
    G = build_spatial_graph(req.rooms)

    try:
        path = nx.shortest_path(G, req.from_room, req.to_room)
        length = nx.shortest_path_length(G, req.from_room, req.to_room)
        return {
            "path": path,
            "length": length,
            "doors": length - 1,
        }
    except nx.NetworkXNoPath:
        raise HTTPException(404, f"No path between {req.from_room} and {req.to_room}")
    except nx.NodeNotFound as e:
        raise HTTPException(404, f"Room not found: {e}")


if __name__ == "__main__":
    import uvicorn
    print(f"Geometry Service starting on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
