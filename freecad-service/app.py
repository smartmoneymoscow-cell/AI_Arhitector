"""
FreeCAD Service — Parametric CAD automation

Capabilities:
  - Parametric building modeling
  - Script execution (FreeCAD Python API)
  - Export to STEP, IFC, STL, OBJ
  - Architectural element creation (walls, slabs, roofs)
  - Section cuts and plan views

Dependencies: freecad (headless)
"""
import os
import uuid
import json
import sys
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(
    title="Architect FreeCAD Service",
    description="Parametric CAD automation with FreeCAD",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PORT = int(os.environ.get("PORT", 8088))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# FreeCAD imports (graceful fallback)
# ═══════════════════════════════════════════════════════════════

FREECAD_AVAILABLE = False
FREECAD_PATH = os.environ.get("FREECAD_PATH", "")

# Try to find FreeCAD Python modules
search_paths = [
    FREECAD_PATH,
    "/usr/lib/freecad/lib",
    "/usr/lib/freecad-python3/lib",
    "/usr/share/freecad/lib",
    "/snap/freecad/current/usr/lib/freecad/lib",
    "/opt/freecad/lib",
]

for p in search_paths:
    if p and os.path.isdir(p) and p not in sys.path:
        sys.path.append(p)

try:
    import FreeCAD
    import Part
    import Arch
    import Draft
    FREECAD_AVAILABLE = True
    print(f"[freecad-service] FreeCAD loaded: {FreeCAD.Version()}")
except ImportError as e:
    print(f"[freecad-service] FreeCAD not available: {e}")


# ═══════════════════════════════════════════════════════════════
# PARAMETRIC BUILDING GENERATION
# ═══════════════════════════════════════════════════════════════

def create_parametric_building(params: dict) -> dict:
    """
    Create a parametric building model using FreeCAD.

    Returns mesh data and analysis.
    """
    if not FREECAD_AVAILABLE:
        return {"error": "FreeCAD not available"}

    width = params.get("width", 10)
    length = params.get("length", 12)
    floors = params.get("floors", 2)
    floor_height = params.get("floor_height", 3.0)
    wall_thickness = params.get("wall_thickness", 0.3)

    # Create new document
    doc = FreeCAD.newDocument("Building")

    # Create walls using Arch module
    walls = []
    for floor in range(floors):
        z_base = floor * floor_height

        # Create wall profiles
        # Front wall
        p1 = FreeCAD.Vector(0, 0, z_base)
        p2 = FreeCAD.Vector(width, 0, z_base)
        p3 = FreeCAD.Vector(width, 0, z_base + floor_height)
        p4 = FreeCAD.Vector(0, 0, z_base + floor_height)

        wire = Draft.makeWire([p1, p2, p3, p4], closed=True)
        wall = Arch.makeWall(wire, height=floor_height, width=wall_thickness)
        wall.Label = f"Wall_Front_{floor}"
        walls.append(wall)

        # Back wall
        p1 = FreeCAD.Vector(0, length, z_base)
        p2 = FreeCAD.Vector(width, length, z_base)
        p3 = FreeCAD.Vector(width, length, z_base + floor_height)
        p4 = FreeCAD.Vector(0, length, z_base + floor_height)

        wire = Draft.makeWire([p1, p2, p3, p4], closed=True)
        wall = Arch.makeWall(wire, height=floor_height, width=wall_thickness)
        wall.Label = f"Wall_Back_{floor}"
        walls.append(wall)

        # Left wall
        p1 = FreeCAD.Vector(0, 0, z_base)
        p2 = FreeCAD.Vector(0, length, z_base)
        p3 = FreeCAD.Vector(0, length, z_base + floor_height)
        p4 = FreeCAD.Vector(0, 0, z_base + floor_height)

        wire = Draft.makeWire([p1, p2, p3, p4], closed=True)
        wall = Arch.makeWall(wire, height=floor_height, width=wall_thickness)
        wall.Label = f"Wall_Left_{floor}"
        walls.append(wall)

        # Right wall
        p1 = FreeCAD.Vector(width, 0, z_base)
        p2 = FreeCAD.Vector(width, length, z_base)
        p3 = FreeCAD.Vector(width, length, z_base + floor_height)
        p4 = FreeCAD.Vector(width, 0, z_base + floor_height)

        wire = Draft.makeWire([p1, p2, p3, p4], closed=True)
        wall = Arch.makeWall(wire, height=floor_height, width=wall_thickness)
        wall.Label = f"Wall_Right_{floor}"
        walls.append(wall)

        # Floor slab
        if floor > 0:
            slab = Arch.makeSlab(
                doc.addObject("Part::Box", f"Slab_{floor}"),
                z=z_base
            )
            slab.Label = f"Slab_{floor}"

    # Recompute
    doc.recompute()

    # Export to STEP
    job_id = uuid.uuid4().hex[:8]
    step_path = os.path.join(OUTPUT_DIR, f"freecad_{job_id}.step")
    stl_path = os.path.join(OUTPUT_DIR, f"freecad_{job_id}.stl")

    try:
        import Import
        objects = [doc.getObject(w.Name) for w in walls if doc.getObject(w.Name)]
        Import.export(objects, step_path)
        Import.export(objects, stl_path)
    except Exception as e:
        return {"error": f"Export failed: {e}"}

    # Cleanup
    FreeCAD.closeDocument(doc.Name)

    return {
        "step_file": step_path,
        "stl_file": stl_path,
        "wall_count": len(walls),
        "floors": floors,
        "dimensions": {"width": width, "length": length, "height": floors * floor_height},
    }


def execute_freecad_script(script: str) -> dict:
    """Execute a FreeCAD Python script."""
    if not FREECAD_AVAILABLE:
        return {"error": "FreeCAD not available"}

    doc = FreeCAD.newDocument("Script")

    try:
        # Create a safe execution environment
        exec_globals = {
            "FreeCAD": FreeCAD,
            "Part": Part,
            "Arch": Arch,
            "Draft": Draft,
            "doc": doc,
        }
        exec(script, exec_globals)
        doc.recompute()

        return {
            "success": True,
            "objects": [obj.Name for obj in doc.Objects],
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            FreeCAD.closeDocument(doc.Name)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    version = "not installed"
    if FREECAD_AVAILABLE:
        try:
            version = str(FreeCAD.Version())
        except Exception:
            version = "unknown"
    return {
        "status": "ok",
        "service": "freecad-service",
        "freecad_available": FREECAD_AVAILABLE,
        "freecad_version": version,
    }


class ParametricBuildingRequest(BaseModel):
    width: float = 10
    length: float = 12
    floors: int = 2
    floor_height: float = 3.0
    wall_thickness: float = 0.3


@app.post("/api/v1/freecad/building")
async def parametric_building(req: ParametricBuildingRequest):
    """Create a parametric building model."""
    result = create_parametric_building(req.model_dump())
    if "error" in result:
        raise HTTPException(500, result["error"])
    return result


class ScriptRequest(BaseModel):
    script: str


@app.post("/api/v1/freecad/execute")
async def execute_script(req: ScriptRequest):
    """Execute a FreeCAD Python script."""
    result = execute_freecad_script(req.script)
    if "error" in result:
        raise HTTPException(500, result["error"])
    return result


if __name__ == "__main__":
    import uvicorn
    print(f"FreeCAD Service starting on port {PORT}")
    print(f"FreeCAD available: {FREECAD_AVAILABLE}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
