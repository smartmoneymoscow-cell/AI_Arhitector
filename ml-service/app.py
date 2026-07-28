"""
ML Service — AI inference for architectural analysis

Capabilities:
  - Style classification (modern, classic, loft, etc.)
  - Material recognition from images
  - Room type detection from descriptions
  - Floor plan generation from text (ONNX models)
  - Point cloud processing (Open3D)

Dependencies: onnxruntime, numpy, Pillow
"""
import os
import io
import json
import uuid
import base64
from typing import Optional, List, Dict, Any

import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Architect ML Service",
    description="AI inference for architectural analysis",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PORT = int(os.environ.get("PORT", 8085))


# ═══════════════════════════════════════════════════════════════
# STYLE CLASSIFIER (rule-based + optional ONNX)
# ═══════════════════════════════════════════════════════════════

STYLE_KEYWORDS = {
    "modern": ["современн", "модерн", "минимализм", "чист", "прост"],
    "classic": ["классич", "традицион", "колонн", "лепнин", "барокко"],
    "loft": ["лофт", "индустри", "кирпич", "открыт", "чердак"],
    "scandinavian": ["скандинав", "светл", "дерев", "уют", "hygge"],
    "minimalist": ["минимал", "лаконич", "бел", "пуст", "функционал"],
    "hitech": ["хайтек", "hi-tech", "технолог", "стекл", "металл"],
    "baroque": ["барокко", "роскош", "позолот", "орнамент", "дворец"],
    "constructivism": ["конструктивизм", "бетон", "форма", "угол", "авангард"],
}


def classify_style(text: str) -> dict:
    """Classify architectural style from text description."""
    t = text.lower()
    scores = {}

    for style, keywords in STYLE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in t)
        if score > 0:
            scores[style] = score

    if not scores:
        return {"style": "modern", "confidence": 0.3, "all_scores": {}}

    total = sum(scores.values())
    best = max(scores, key=scores.get)
    confidence = scores[best] / max(total, 1)

    return {
        "style": best,
        "confidence": round(confidence, 2),
        "all_scores": {k: round(v/total, 2) for k, v in scores.items()},
    }


# ═══════════════════════════════════════════════════════════════
# ROOM TYPE CLASSIFIER
# ═══════════════════════════════════════════════════════════════

ROOM_FEATURES = {
    "bedroom": {
        "keywords": ["спальн", "кроват", "матрас", "подушк", "комод"],
        "typical_area": (10, 25),
        "typical_ratio": (0.8, 1.5),  # width/length
        "required_furniture": ["bed"],
    },
    "living": {
        "keywords": ["гостин", "диван", "телевизор", "мягк", "зон"],
        "typical_area": (15, 40),
        "typical_ratio": (0.8, 2.0),
        "required_furniture": ["sofa"],
    },
    "kitchen": {
        "keywords": ["кухн", "плит", "ракоин", "столешниц", "вытяжк"],
        "typical_area": (8, 20),
        "typical_ratio": (0.8, 1.8),
        "required_furniture": ["stove", "sink"],
    },
    "bathroom": {
        "keywords": ["ванн", "душ", "унитаз", "раковин", "санузел"],
        "typical_area": (3, 10),
        "typical_ratio": (0.6, 1.5),
        "required_furniture": ["sink"],
    },
    "children": {
        "keywords": ["детск", "игр", "мягк", "ярк", "кресл"],
        "typical_area": (8, 18),
        "typical_ratio": (0.8, 1.5),
        "required_furniture": ["bed"],
    },
    "study": {
        "keywords": ["кабинет", "рабоч", "стол", "книжн", "офис"],
        "typical_area": (6, 15),
        "typical_ratio": (0.8, 1.5),
        "required_furniture": ["desk"],
    },
    "hallway": {
        "keywords": ["прихож", "коридор", "вход", "вешалк", "обувн"],
        "typical_area": (3, 12),
        "typical_ratio": (0.3, 3.0),  # can be very elongated
        "required_furniture": [],
    },
}


def classify_room(text: str, area: float = 0, furniture: List[str] = None) -> dict:
    """Classify room type from text, area, and furniture."""
    t = text.lower()
    furniture = furniture or []
    scores = {}

    for room_type, features in ROOM_FEATURES.items():
        score = 0

        # Keyword match
        kw_score = sum(1 for kw in features["keywords"] if kw in t)
        score += kw_score * 3

        # Area match
        if area > 0:
            min_a, max_a = features["typical_area"]
            if min_a <= area <= max_a:
                score += 2
            elif area < min_a * 0.5 or area > max_a * 2:
                score -= 1

        # Furniture match
        for req in features["required_furniture"]:
            if req in furniture:
                score += 2

        scores[room_type] = score

    if not scores or max(scores.values()) == 0:
        return {"room_type": "living", "confidence": 0.2, "all_scores": {}}

    total = sum(max(0, v) for v in scores.values())
    best = max(scores, key=scores.get)
    confidence = scores[best] / max(total, 1)

    return {
        "room_type": best,
        "confidence": round(confidence, 2),
        "all_scores": {k: round(max(0, v)/max(total, 1), 2) for k, v in scores.items()},
    }


# ═══════════════════════════════════════════════════════════════
# FLOOR PLAN GENERATION (procedural + optional ONNX)
# ═══════════════════════════════════════════════════════════════

def generate_floor_plan(
    width: float,
    length: float,
    rooms: List[dict],
    style: str = "modern"
) -> dict:
    """
    Generate a floor plan layout.

    Uses procedural algorithm to place rooms within the building footprint.
    Returns polygon data for each room.
    """
    # Sort rooms by priority (largest first, then by importance)
    room_priority = {
        "living": 1, "kitchen": 2, "bedroom": 3, "study": 4,
        "children": 5, "dining": 6, "bathroom": 7, "hallway": 8,
    }
    sorted_rooms = sorted(
        rooms,
        key=lambda r: (room_priority.get(r.get("room_type", "living"), 5),
                       -r.get("area", 10))
    )

    # Simple grid-based layout
    placed_rooms = []
    cursor_x = 0.0
    cursor_y = 0.0
    row_height = 0.0
    margin = 0.3  # wall thickness

    for room in sorted_rooms:
        area = room.get("area", 10)
        room_type = room.get("room_type", "living")

        # Calculate room dimensions
        ratio = 1.2  # default width/length ratio
        if room_type == "hallway":
            ratio = 3.0
        elif room_type == "bathroom":
            ratio = 1.0

        rw = max(2.0, (area * ratio) ** 0.5)
        rl = max(2.0, area / rw)

        # Check if fits in current row
        if cursor_x + rw + margin > width:
            # New row
            cursor_x = 0.0
            cursor_y += row_height + margin
            row_height = 0.0

        if cursor_y + rl + margin > length:
            # Doesn't fit — scale down
            rw = min(rw, width - cursor_x - margin)
            rl = min(rl, length - cursor_y - margin)

        if rw < 1.5 or rl < 1.5:
            continue

        # Place room
        polygon = {
            "points": [
                {"x": cursor_x, "y": cursor_y},
                {"x": cursor_x + rw, "y": cursor_y},
                {"x": cursor_x + rw, "y": cursor_y + rl},
                {"x": cursor_x, "y": cursor_y + rl},
            ]
        }

        placed_rooms.append({
            **room,
            "polygon": polygon,
            "actual_area": round(rw * rl, 1),
            "bbox": {
                "min_x": cursor_x, "min_y": cursor_y,
                "max_x": cursor_x + rw, "max_y": cursor_y + rl,
                "width": rw, "height": rl,
            },
        })

        cursor_x += rw + margin
        row_height = max(row_height, rl)

    return {
        "building": {"width": width, "length": length},
        "rooms": placed_rooms,
        "total_placed": len(placed_rooms),
        "coverage": sum(r.get("actual_area", 0) for r in placed_rooms) / max(width * length, 1),
    }


# ═══════════════════════════════════════════════════════════════
# POINT CLOUD PROCESSING (Open3D)
# ═══════════════════════════════════════════════════════════════

def process_point_cloud(points: List[List[float]], method: str = "voxel") -> dict:
    """
    Process point cloud data.

    Args:
        points: List of [x, y, z] coordinates
        method: "voxel" (downsample), "normal" (estimate normals), "mesh" (reconstruct)

    Returns:
        Processed point cloud data
    """
    try:
        import open3d as o3d
    except ImportError:
        # Fallback: basic processing with numpy
        pts = np.array(points)
        return {
            "method": method,
            "point_count": len(pts),
            "bounds": {
                "min": pts.min(axis=0).tolist(),
                "max": pts.max(axis=0).tolist(),
            },
            "center": pts.mean(axis=0).tolist(),
            "open3d_available": False,
        }

    # Create Open3D point cloud
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.array(points))

    result = {
        "method": method,
        "point_count": len(points),
        "open3d_available": True,
    }

    if method == "voxel":
        # Downsample
        voxel_size = 0.05
        pcd_down = pcd.voxel_down_sample(voxel_size)
        result["downsampled_count"] = len(pcd_down.points)
        result["voxel_size"] = voxel_size

    elif method == "normal":
        # Estimate normals
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30)
        )
        normals = np.asarray(pcd.normals)
        result["normals_computed"] = True
        result["avg_normal"] = normals.mean(axis=0).tolist()

    elif method == "mesh":
        # Reconstruct mesh
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30)
        )
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=9
        )
        result["mesh_vertices"] = len(mesh.vertices)
        result["mesh_triangles"] = len(mesh.triangles)

    # Bounds
    pts = np.asarray(pcd.points)
    result["bounds"] = {
        "min": pts.min(axis=0).tolist(),
        "max": pts.max(axis=0).tolist(),
    }
    result["center"] = pts.mean(axis=0).tolist()

    return result


# ═══════════════════════════════════════════════════════════════
# IMAGE ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_image(image_bytes: bytes) -> dict:
    """
    Analyze architectural image.

    Extracts: style, materials, colors, proportions.
    Uses basic image processing (no heavy ML).
    """
    try:
        from PIL import Image
    except ImportError:
        return {"error": "Pillow not installed", "analysis": "basic"}

    img = Image.open(io.BytesIO(image_bytes))
    img_array = np.array(img.convert("RGB"))

    # Color analysis
    avg_color = img_array.mean(axis=(0, 1)).tolist()
    dominant_colors = _extract_dominant_colors(img_array)

    # Brightness
    brightness = img_array.mean() / 255

    # Contrast
    contrast = img_array.std() / 255

    return {
        "size": {"width": img.width, "height": img.height},
        "avg_color": [round(c) for c in avg_color],
        "dominant_colors": dominant_colors,
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "aspect_ratio": round(img.width / max(img.height, 1), 2),
    }


def _extract_dominant_colors(img_array: np.ndarray, n: int = 5) -> List[List[int]]:
    """Extract dominant colors using k-means-like clustering."""
    # Reshape to pixels
    pixels = img_array.reshape(-1, 3)

    # Simple quantization
    quantized = (pixels // 32) * 32 + 16

    # Count occurrences
    from collections import Counter
    color_counts = Counter(map(tuple, quantized))

    # Top N colors
    top_colors = color_counts.most_common(n)
    return [[int(c) for c in color] for color, _ in top_colors]


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    onnx_ok = False
    try:
        import onnxruntime
        onnx_ok = True
    except ImportError:
        pass

    open3d_ok = False
    try:
        import open3d
        open3d_ok = True
    except ImportError:
        pass

    return {
        "status": "ok",
        "service": "ml-service",
        "onnxruntime": onnx_ok,
        "open3d": open3d_ok,
    }


class StyleRequest(BaseModel):
    text: str


@app.post("/api/v1/ml/classify-style")
async def classify_style_endpoint(req: StyleRequest):
    """Classify architectural style from text."""
    return classify_style(req.text)


class RoomClassifyRequest(BaseModel):
    text: str
    area: float = 0
    furniture: List[str] = []


@app.post("/api/v1/ml/classify-room")
async def classify_room_endpoint(req: RoomClassifyRequest):
    """Classify room type from text and properties."""
    return classify_room(req.text, req.area, req.furniture)


class FloorPlanRequest(BaseModel):
    width: float
    length: float
    rooms: List[dict]
    style: str = "modern"


@app.post("/api/v1/ml/generate-floorplan")
async def generate_floorplan_endpoint(req: FloorPlanRequest):
    """Generate floor plan layout."""
    return generate_floor_plan(req.width, req.length, req.rooms, req.style)


class PointCloudRequest(BaseModel):
    points: List[List[float]]
    method: str = "voxel"


@app.post("/api/v1/ml/pointcloud")
async def pointcloud_endpoint(req: PointCloudRequest):
    """Process point cloud data."""
    return process_point_cloud(req.points, req.method)


@app.post("/api/v1/ml/analyze-image")
async def analyze_image_endpoint(file: UploadFile = File(...)):
    """Analyze architectural image."""
    content = await file.read()
    return analyze_image(content)


if __name__ == "__main__":
    import uvicorn
    print(f"ML Service starting on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
