"""
CAD Service — Solid modeling with OpenCascade (OCCT) via pythonocc-core

Capabilities:
  - Boolean operations (union, intersection, difference)
  - Solid primitives (box, sphere, cylinder, cone, torus)
  - Extrusion, revolution, sweeping
  - Filleting, chamfering
  - Shape analysis (volume, area, center of mass)
  - STEP/IGES export
  - Mesh generation (tessellation)

Dependencies: pythonocc-core (OpenCascade Python bindings)
"""
import os
import uuid
import json
import math
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

app = FastAPI(
    title="Architect CAD Service",
    description="Solid modeling with OpenCascade (OCCT)",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PORT = int(os.environ.get("PORT", 8087))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# OpenCascade imports (graceful fallback)
# ═══════════════════════════════════════════════════════════════

OCCT_AVAILABLE = False
try:
    from OCP.BRepPrimAPI import (
        BRepPrimAPI_MakeBox, BRepPrimAPI_MakeSphere,
        BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeCone,
        BRepPrimAPI_MakeTorus, BRepPrimAPI_MakePrism,
        BRepPrimAPI_MakeRevol,
    )
    from OCP.BRepAlgoAPI import (
        BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common,
    )
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeEdge, BRepBuilderAPI_Transform,
    )
    from OCP.GC import GC_MakeSegment
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Trsf, gp_Vec
    from OCP.TopoDS import TopoDS_Shape, TopoDS_Compound
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.StlAPI import StlAPI_Writer
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.ShapeAnalysis import ShapeAnalysis_ShapeProperties
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX

    OCCT_AVAILABLE = True
    print("[cad-service] OpenCascade (OCCT) loaded successfully")
except ImportError as e:
    print(f"[cad-service] OpenCascade not available: {e}")
    print("[cad-service] Install pythonocc-core for full functionality")


# ═══════════════════════════════════════════════════════════════
# PRIMITIVES
# ═══════════════════════════════════════════════════════════════

def make_box(width: float, height: float, depth: float):
    """Create a box solid."""
    if not OCCT_AVAILABLE:
        return None
    return BRepPrimAPI_MakeBox(width, height, depth).Shape()


def make_sphere(radius: float):
    """Create a sphere solid."""
    if not OCCT_AVAILABLE:
        return None
    return BRepPrimAPI_MakeSphere(radius).Shape()


def make_cylinder(radius: float, height: float):
    """Create a cylinder solid."""
    if not OCCT_AVAILABLE:
        return None
    return BRepPrimAPI_MakeCylinder(radius, height).Shape()


def make_cone(radius1: float, radius2: float, height: float):
    """Create a cone/conical frustum solid."""
    if not OCCT_AVAILABLE:
        return None
    return BRepPrimAPI_MakeCone(radius1, radius2, height).Shape()


def make_torus(radius_major: float, radius_minor: float):
    """Create a torus solid."""
    if not OCCT_AVAILABLE:
        return None
    return BRepPrimAPI_MakeTorus(radius_major, radius_minor).Shape()


# ═══════════════════════════════════════════════════════════════
# BOOLEAN OPERATIONS
# ═══════════════════════════════════════════════════════════════

def boolean_union(shape1, shape2):
    """Union of two shapes."""
    if not OCCT_AVAILABLE:
        return None
    return BRepAlgoAPI_Fuse(shape1, shape2).Shape()


def boolean_cut(shape1, shape2):
    """Cut shape2 from shape1."""
    if not OCCT_AVAILABLE:
        return None
    return BRepAlgoAPI_Cut(shape1, shape2).Shape()


def boolean_intersection(shape1, shape2):
    """Intersection of two shapes."""
    if not OCCT_AVAILABLE:
        return None
    return BRepAlgoAPI_Common(shape1, shape2).Shape()


# ═══════════════════════════════════════════════════════════════
# FEATURES
# ═══════════════════════════════════════════════════════════════

def fillet(shape, radius: float):
    """Apply fillet (round edges) to shape."""
    if not OCCT_AVAILABLE:
        return None
    fillet_maker = BRepFilletAPI_MakeFillet(shape)
    # Add all edges
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        fillet_maker.Add(explorer.Current())
        explorer.Next()
    fillet_maker.Build()
    return fillet_maker.Shape()


def extrude_face(face, direction: tuple, distance: float):
    """Extrude a face along a direction."""
    if not OCCT_AVAILABLE:
        return None
    vec = gp_Vec(*direction)
    vec.Scale(distance)
    return BRepPrimAPI_MakePrism(face, vec).Shape()


def revolve_face(face, axis_point: tuple, axis_dir: tuple, angle: float = 360):
    """Revolve a face around an axis."""
    if not OCCT_AVAILABLE:
        return None
    ax = gp_Ax2(gp_Pnt(*axis_point), gp_Dir(*axis_dir))
    return BRepPrimAPI_MakeRevol(face, ax, math.radians(angle)).Shape()


def translate(shape, dx: float, dy: float, dz: float):
    """Translate a shape."""
    if not OCCT_AVAILABLE:
        return None
    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(dx, dy, dz))
    return BRepBuilderAPI_Transform(shape, trsf).Shape()


# ═══════════════════════════════════════════════════════════════
# SHAPE ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_shape(shape) -> dict:
    """Analyze shape properties: volume, area, center of mass."""
    if not OCCT_AVAILABLE:
        return {"error": "OCCT not available"}

    props = GProp_GProps()
    BRepGProp.VolumeProperties(shape, props)
    volume = props.Mass()
    center = props.CentreOfMass()

    area_props = GProp_GProps()
    BRepGProp.SurfaceProperties(shape, area_props)
    area = area_props.Mass()

    # Count topology
    face_count = 0
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face_count += 1
        explorer.Next()

    edge_count = 0
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        edge_count += 1
        explorer.Next()

    return {
        "volume": round(volume, 4),
        "area": round(area, 4),
        "center_of_mass": {
            "x": round(center.X(), 4),
            "y": round(center.Y(), 4),
            "z": round(center.Z(), 4),
        },
        "topology": {
            "faces": face_count,
            "edges": edge_count,
        }
    }


# ═══════════════════════════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════════════════════════

def export_step(shape, filepath: str) -> bool:
    """Export shape to STEP format."""
    if not OCCT_AVAILABLE:
        return False
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(filepath)
    return status == IFSelect_RetDone


def export_stl(shape, filepath: str, linear_deflection: float = 0.1) -> bool:
    """Export shape to STL format (tessellation)."""
    if not OCCT_AVAILABLE:
        return False
    mesh = BRepMesh_IncrementalMesh(shape, linear_deflection)
    mesh.Perform()
    writer = StlAPI_Writer()
    writer.Write(filepath)
    return True


def shape_to_mesh(shape, linear_deflection: float = 0.1) -> dict:
    """Convert shape to triangle mesh (vertices + faces)."""
    if not OCCT_AVAILABLE:
        return {"error": "OCCT not available"}

    mesh = BRepMesh_IncrementalMesh(shape, linear_deflection)
    mesh.Perform()

    vertices = []
    triangles = []

    # Extract triangulation from faces
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    vertex_offset = 0
    while explorer.More():
        face = explorer.Current()
        location = face.Location()
        tri = BRep_Tool.Triangulation_s(face, location)

        if tri is not None:
            # Get vertices
            for i in range(1, tri.NbNodes() + 1):
                node = tri.Node(i)
                vertices.append([node.X(), node.Y(), node.Z()])

            # Get triangles
            for i in range(1, tri.NbTriangles() + 1):
                tri_nodes = tri.Triangle(i)
                n1, n2, n3 = tri_nodes.Get()
                triangles.append([
                    n1 - 1 + vertex_offset,
                    n2 - 1 + vertex_offset,
                    n3 - 1 + vertex_offset,
                ])

            vertex_offset += tri.NbNodes()

        explorer.Next()

    return {
        "vertices": vertices,
        "triangles": triangles,
        "vertex_count": len(vertices),
        "triangle_count": len(triangles),
    }


# ═══════════════════════════════════════════════════════════════
# BUILDING GENERATION (high-level)
# ═══════════════════════════════════════════════════════════════

def generate_building_solid(params: dict) -> dict:
    """
    Generate a building as an OCCT solid model.

    Creates walls, floors, roof as separate solids, then combines.
    Returns mesh data for Three.js visualization.
    """
    if not OCCT_AVAILABLE:
        return {"error": "OCCT not available"}

    width = params.get("width", 10)
    length = params.get("length", 12)
    floors = params.get("floors", 2)
    floor_height = params.get("floor_height", 3.0)
    wall_thickness = params.get("wall_thickness", 0.3)
    roof_type = params.get("roof_type", "gabled")

    shapes = []

    # Foundation
    foundation = make_box(
        width + 0.6, 0.3, length + 0.6
    )
    foundation = translate(foundation, -0.3, -0.15, -0.3)
    shapes.append({"name": "Foundation", "shape": foundation})

    # Walls per floor
    for floor in range(floors):
        z_base = floor * floor_height + 0.15

        # Front wall
        front = make_box(width, wall_thickness, floor_height)
        front = translate(front, 0, -wall_thickness / 2, z_base)
        shapes.append({"name": f"Wall_Front_{floor}", "shape": front})

        # Back wall
        back = make_box(width, wall_thickness, floor_height)
        back = translate(back, 0, length - wall_thickness / 2, z_base)
        shapes.append({"name": f"Wall_Back_{floor}", "shape": back})

        # Left wall
        left = make_box(wall_thickness, length, floor_height)
        left = translate(left, -wall_thickness / 2, 0, z_base)
        shapes.append({"name": f"Wall_Left_{floor}", "shape": left})

        # Right wall
        right = make_box(wall_thickness, length, floor_height)
        right = translate(right, width - wall_thickness / 2, 0, z_base)
        shapes.append({"name": f"Wall_Right_{floor}", "shape": right})

        # Floor slab (not for ground floor)
        if floor > 0:
            slab = make_box(width, 0.2, length)
            slab = translate(slab, 0, 0, floor * floor_height)
            shapes.append({"name": f"Slab_{floor}", "shape": slab})

        # Windows (cut from front wall)
        n_windows = max(2, width // 3)
        for i in range(n_windows):
            wx = (i + 1) * width / (n_windows + 1) - 0.6
            wz = z_base + floor_height * 0.35
            window = make_box(1.2, wall_thickness + 0.1, 1.5)
            window = translate(window, wx, -wall_thickness / 2 - 0.05, wz)
            shapes.append({"name": f"Window_{floor}_{i}", "shape": window, "is_cut": True})

    # Door (cut from front wall)
    door = make_box(0.9, wall_thickness + 0.1, 2.1)
    door = translate(door, width / 2 - 0.45, -wall_thickness / 2 - 0.05, 0.15)
    shapes.append({"name": "Door", "shape": door, "is_cut": True})

    # Roof
    total_h = floors * floor_height + 0.15
    if roof_type == "flat":
        roof = make_box(width + 0.6, 0.15, length + 0.6)
        roof = translate(roof, -0.3, 0, total_h)
        shapes.append({"name": "Roof", "shape": roof})

    # Combine: union all solids, then cut windows/doors
    result = None
    solid_shapes = [s for s in shapes if not s.get("is_cut")]
    cut_shapes = [s for s in shapes if s.get("is_cut")]

    for s in solid_shapes:
        if result is None:
            result = s["shape"]
        else:
            result = boolean_union(result, s["shape"])

    for s in cut_shapes:
        if result is not None:
            result = boolean_cut(result, s["shape"])

    if result is None:
        return {"error": "Failed to generate building"}

    # Analyze
    analysis = analyze_shape(result)

    # Convert to mesh
    mesh = shape_to_mesh(result, linear_deflection=0.05)

    return {
        "analysis": analysis,
        "mesh": mesh,
        "part_count": len(shapes),
    }


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "cad-service",
        "occt_available": OCCT_AVAILABLE,
        "version": "1.0.0",
    }


class PrimitiveRequest(BaseModel):
    type: str  # "box", "sphere", "cylinder", "cone", "torus"
    params: dict = {}


@app.post("/api/v1/cad/primitive")
async def create_primitive(req: PrimitiveRequest):
    """Create a primitive solid."""
    if not OCCT_AVAILABLE:
        raise HTTPException(500, "OpenCascade not installed")

    p = req.params
    shape = None

    if req.type == "box":
        shape = make_box(p.get("width", 1), p.get("height", 1), p.get("depth", 1))
    elif req.type == "sphere":
        shape = make_sphere(p.get("radius", 1))
    elif req.type == "cylinder":
        shape = make_cylinder(p.get("radius", 1), p.get("height", 1))
    elif req.type == "cone":
        shape = make_cone(p.get("radius1", 1), p.get("radius2", 0.5), p.get("height", 1))
    elif req.type == "torus":
        shape = make_torus(p.get("radius_major", 1), p.get("radius_minor", 0.3))
    else:
        raise HTTPException(400, f"Unknown primitive type: {req.type}")

    analysis = analyze_shape(shape)
    mesh = shape_to_mesh(shape)

    return {"type": req.type, "analysis": analysis, "mesh": mesh}


class BooleanRequest(BaseModel):
    operation: str  # "union", "cut", "intersection"
    shape1_type: str = "box"
    shape1_params: dict = {}
    shape2_type: str = "sphere"
    shape2_params: dict = {}
    shape2_offset: dict = {}


@app.post("/api/v1/cad/boolean")
async def boolean_operation(req: BooleanRequest):
    """Perform boolean operation between two primitives."""
    if not OCCT_AVAILABLE:
        raise HTTPException(500, "OpenCascade not installed")

    # Create shapes
    s1 = None
    s2 = None

    p1 = req.shape1_params
    if req.shape1_type == "box":
        s1 = make_box(p1.get("width", 1), p1.get("height", 1), p1.get("depth", 1))
    elif req.shape1_type == "sphere":
        s1 = make_sphere(p1.get("radius", 1))
    elif req.shape1_type == "cylinder":
        s1 = make_cylinder(p1.get("radius", 1), p1.get("height", 1))

    p2 = req.shape2_params
    if req.shape2_type == "box":
        s2 = make_box(p2.get("width", 1), p2.get("height", 1), p2.get("depth", 1))
    elif req.shape2_type == "sphere":
        s2 = make_sphere(p2.get("radius", 1))
    elif req.shape2_type == "cylinder":
        s2 = make_cylinder(p2.get("radius", 1), p2.get("height", 1))

    if s1 is None or s2 is None:
        raise HTTPException(400, "Could not create shapes")

    # Apply offset to shape2
    offset = req.shape2_offset
    if offset:
        s2 = translate(s2,
                       offset.get("x", 0),
                       offset.get("y", 0),
                       offset.get("z", 0))

    # Perform operation
    result = None
    if req.operation == "union":
        result = boolean_union(s1, s2)
    elif req.operation == "cut":
        result = boolean_cut(s1, s2)
    elif req.operation == "intersection":
        result = boolean_intersection(s1, s2)
    else:
        raise HTTPException(400, f"Unknown operation: {req.operation}")

    analysis = analyze_shape(result)
    mesh = shape_to_mesh(result)

    return {"operation": req.operation, "analysis": analysis, "mesh": mesh}


class FilletRequest(BaseModel):
    shape_type: str = "box"
    shape_params: dict = {}
    radius: float = 0.1


@app.post("/api/v1/cad/fillet")
async def fillet_shape(req: FilletRequest):
    """Apply fillet to a shape."""
    if not OCCT_AVAILABLE:
        raise HTTPException(500, "OpenCascade not installed")

    p = req.shape_params
    shape = None
    if req.shape_type == "box":
        shape = make_box(p.get("width", 1), p.get("height", 1), p.get("depth", 1))

    if shape is None:
        raise HTTPException(400, "Could not create shape")

    result = fillet(shape, req.radius)
    analysis = analyze_shape(result)
    mesh = shape_to_mesh(result)

    return {"analysis": analysis, "mesh": mesh}


class BuildingRequest(BaseModel):
    width: float = 10
    length: float = 12
    floors: int = 2
    floor_height: float = 3.0
    wall_thickness: float = 0.3
    roof_type: str = "gabled"


@app.post("/api/v1/cad/building")
async def generate_building(req: BuildingRequest):
    """Generate a building as OCCT solid model."""
    if not OCCT_AVAILABLE:
        raise HTTPException(500, "OpenCascade not installed")

    params = req.model_dump()
    result = generate_building_solid(params)
    return result


class ExportRequest(BaseModel):
    shape_type: str = "box"
    shape_params: dict = {}
    format: str = "step"  # "step" or "stl"


@app.post("/api/v1/cad/export")
async def export_shape(req: ExportRequest):
    """Export shape to STEP or STL format."""
    if not OCCT_AVAILABLE:
        raise HTTPException(500, "OpenCascade not installed")

    p = req.shape_params
    shape = None
    if req.shape_type == "box":
        shape = make_box(p.get("width", 1), p.get("height", 1), p.get("depth", 1))
    elif req.shape_type == "sphere":
        shape = make_sphere(p.get("radius", 1))
    elif req.shape_type == "cylinder":
        shape = make_cylinder(p.get("radius", 1), p.get("height", 1))

    if shape is None:
        raise HTTPException(400, "Could not create shape")

    job_id = uuid.uuid4().hex[:8]

    if req.format == "step":
        filepath = os.path.join(OUTPUT_DIR, f"{job_id}.step")
        export_step(shape, filepath)
        return FileResponse(filepath, media_type="application/step",
                           filename=f"model_{job_id}.step")
    elif req.format == "stl":
        filepath = os.path.join(OUTPUT_DIR, f"{job_id}.stl")
        export_stl(shape, filepath)
        return FileResponse(filepath, media_type="application/sla",
                           filename=f"model_{job_id}.stl")
    else:
        raise HTTPException(400, f"Unknown format: {req.format}")


if __name__ == "__main__":
    import uvicorn
    print(f"CAD Service starting on port {PORT}")
    print(f"OpenCascade available: {OCCT_AVAILABLE}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
