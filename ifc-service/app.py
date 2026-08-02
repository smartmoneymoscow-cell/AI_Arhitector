"""
IFC Service — Building Information Modeling with IfcOpenShell

Capabilities:
  - Generate IFC files from Building model
  - Import/parse IFC files
  - Extract building data (rooms, walls, doors, windows)
  - Export to IFC2x3 and IFC4

Dependencies: ifcopenshell, numpy
"""
import os
import uuid
import tempfile
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

app = FastAPI(
    title="Architect IFC Service",
    description="IFC import/export with IfcOpenShell",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PORT = int(os.environ.get("PORT", 8084))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# IFC GENERATION
# ═══════════════════════════════════════════════════════════════

def generate_ifc(building: dict, version: str = "IFC2X3") -> str:
    """
    Generate IFC file from Building model.

    Args:
        building: Building dict with floors, rooms, walls, etc.
        version: "IFC2X3" or "IFC4"

    Returns:
        Path to generated IFC file
    """
    try:
        import ifcopenshell
        import ifcopenshell.api
    except ImportError:
        raise HTTPException(500, "ifcopenshell not installed")

    # Create IFC file
    ifc = ifcopenshell.file(schema=version)

    # Create basic structure
    owner = ifcopenshell.api.run("owner.add_owner_history", ifc)
    context = ifcopenshell.api.run("context.add_context", ifc,
                                   context_type="Model")
    body = ifcopenshell.api.run("context.add_context", ifc,
                                context_type="Model",
                                context_identifier="Body",
                                target_view="MODEL_VIEW",
                                parent=context)

    # Create site
    site = ifcopenshell.api.run("root.create_entity", ifc,
                                ifc_class="IfcSite", name="Site")
    ifcopenshell.api.run("aggregate.assign_object", ifc,
                         objects=[site], relating_object=context)

    # Create building
    ifc_building = ifcopenshell.api.run("root.create_entity", ifc,
                                        ifc_class="IfcBuilding",
                                        name=building.get("name", "Building"))
    ifcopenshell.api.run("aggregate.assign_object", ifc,
                         objects=[ifc_building], relating_object=site)

    # Process floors
    for floor_data in building.get("floors", []):
        floor_level = floor_data.get("level", 0)
        floor_height = floor_data.get("height", 3.0)
        elevation = floor_data.get("elevation", floor_level * floor_height)

        # Create storey
        storey = ifcopenshell.api.run("root.create_entity", ifc,
                                      ifc_class="IfcBuildingStorey",
                                      name=f"Floor {floor_level}")
        storey.Elevation = elevation
        ifcopenshell.api.run("aggregate.assign_object", ifc,
                             objects=[storey], relating_object=ifc_building)

        # Process rooms
        for room_data in floor_data.get("rooms", []):
            room = ifcopenshell.api.run("root.create_entity", ifc,
                                        ifc_class="IfcSpace",
                                        name=room_data.get("name", "Room"))
            room.LongName = room_data.get("room_type", "")
            room.ElevationOfElevation = elevation
            ifcopenshell.api.run("spatial.assign_container", ifc,
                                 products=[room], relating_structure=storey)

            # Add room geometry (simplified as extruded polygon)
            polygon = room_data.get("polygon", {})
            points = polygon.get("points", [])
            if len(points) >= 3:
                try:
                    # Create profile from room polygon
                    profile_points = [(p["x"], p["y"]) for p in points]
                    profile_points.append(profile_points[0])  # close polygon

                    # Create IfcArbitraryClosedProfileDef
                    polyline = ifc.createIfcPolyline(
                        [ifc.createIfcCartesianPoint(p) for p in profile_points]
                    )
                    profile = ifc.createIfcArbitraryClosedProfileDef(
                        "AREA", None, polyline
                    )

                    # Extrude to room height
                    extrusion = ifc.createIfcExtrudedAreaSolid(
                        profile,
                        ifc.createIfcAxis2Placement3D(
                            ifc.createIfcCartesianPoint((0, 0, elevation))
                        ),
                        ifc.createIfcDirection((0, 0, 1)),
                        room_data.get("height", floor_height)
                    )

                    # Assign geometry
                    representation = ifc.createIfcShapeRepresentation(
                        body, "Body", "SweptSolid", [extrusion]
                    )
                    ifcopenshell.api.run("geometry.assign_representation", ifc,
                                         product=room,
                                         representation=representation)
                except Exception as e:
                    print(f"[ifc-service] Room geometry error: {e}")

        # Process walls
        for wall_data in floor_data.get("walls", []):
            wall = ifcopenshell.api.run("root.create_entity", ifc,
                                        ifc_class="IfcWall",
                                        name=wall_data.get("id", "Wall"))

            start = wall_data.get("start", {})
            end = wall_data.get("end", {})
            thickness = wall_data.get("thickness", 0.3)
            height = wall_data.get("height", floor_height)

            if start and end:
                try:
                    # Create wall as extruded rectangle
                    sx, sy = start.get("x", 0), start.get("y", 0)
                    ex, ey = end.get("x", 1), end.get("y", 0)

                    # Wall direction
                    dx, dy = ex - sx, ey - sy
                    length = (dx**2 + dy**2) ** 0.5
                    if length < 0.01:
                        continue

                    # Perpendicular for thickness
                    nx_, ny_ = -dy/length * thickness/2, dx/length * thickness/2

                    wall_points = [
                        (sx + nx_, sy + ny_),
                        (ex + nx_, ey + ny_),
                        (ex - nx_, ey - ny_),
                        (sx - nx_, sy - ny_),
                        (sx + nx_, sy + ny_),  # close
                    ]

                    polyline = ifc.createIfcPolyline(
                        [ifc.createIfcCartesianPoint(p) for p in wall_points]
                    )
                    profile = ifc.createIfcArbitraryClosedProfileDef(
                        "AREA", None, polyline
                    )
                    extrusion = ifc.createIfcExtrudedAreaSolid(
                        profile,
                        ifc.createIfcAxis2Placement3D(
                            ifc.createIfcCartesianPoint((0, 0, elevation))
                        ),
                        ifc.createIfcDirection((0, 0, 1)),
                        height
                    )
                    representation = ifc.createIfcShapeRepresentation(
                        body, "Body", "SweptSolid", [extrusion]
                    )
                    ifcopenshell.api.run("geometry.assign_representation", ifc,
                                         product=wall,
                                         representation=representation)
                    ifcopenshell.api.run("spatial.assign_container", ifc,
                                         products=[wall], relating_structure=storey)
                except Exception as e:
                    print(f"[ifc-service] Wall geometry error: {e}")

    # Save to file
    job_id = uuid.uuid4().hex[:8]
    output_path = os.path.join(OUTPUT_DIR, f"architect_{job_id}.ifc")
    ifc.write(output_path)

    return output_path


def parse_ifc(file_path: str) -> dict:
    """Parse IFC file and extract building data."""
    try:
        import ifcopenshell
    except ImportError:
        raise HTTPException(500, "ifcopenshell not installed")

    ifc = ifcopenshell.open(file_path)

    result = {
        "schema": ifc.schema,
        "project": None,
        "sites": [],
        "buildings": [],
        "storeys": [],
        "spaces": [],
        "walls": [],
        "doors": [],
        "windows": [],
        "total_elements": 0,
    }

    # Extract project
    projects = ifc.by_type("IfcProject")
    if projects:
        result["project"] = {"name": projects[0].Name, "id": projects[0].GlobalId}

    # Extract sites
    for site in ifc.by_type("IfcSite"):
        result["sites"].append({
            "id": site.GlobalId,
            "name": site.Name,
            "latitude": getattr(site, "RefLatitude", None),
            "longitude": getattr(site, "RefLongitude", None),
        })

    # Extract buildings
    for bld in ifc.by_type("IfcBuilding"):
        result["buildings"].append({
            "id": bld.GlobalId,
            "name": bld.Name,
            "elevation": getattr(bld, "ElevationOfRefHeight", 0),
        })

    # Extract storeys
    for storey in ifc.by_type("IfcBuildingStorey"):
        result["storeys"].append({
            "id": storey.GlobalId,
            "name": storey.Name,
            "elevation": storey.Elevation,
        })

    # Extract spaces (rooms)
    for space in ifc.by_type("IfcSpace"):
        result["spaces"].append({
            "id": space.GlobalId,
            "name": space.Name,
            "long_name": space.LongName,
            "elevation": getattr(space, "ElevationOfElevation", 0),
        })

    # Extract walls
    for wall in ifc.by_type("IfcWall"):
        result["walls"].append({
            "id": wall.GlobalId,
            "name": wall.Name,
        })

    # Extract doors
    for door in ifc.by_type("IfcDoor"):
        result["doors"].append({
            "id": door.GlobalId,
            "name": door.Name,
            "width": getattr(door, "OverallWidth", None),
            "height": getattr(door, "OverallHeight", None),
        })

    # Extract windows
    for win in ifc.by_type("IfcWindow"):
        result["windows"].append({
            "id": win.GlobalId,
            "name": win.Name,
            "width": getattr(win, "OverallWidth", None),
            "height": getattr(win, "OverallHeight", None),
        })

    result["total_elements"] = (
        len(result["walls"]) + len(result["doors"]) +
        len(result["windows"]) + len(result["spaces"])
    )

    return result


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    try:
        import ifcopenshell
        ifc_version = ifcopenshell.version
    except ImportError:
        ifc_version = "not installed"
    return {"status": "ok", "service": "ifc-service", "ifcopenshell": ifc_version}


class GenerateIFCRequest(BaseModel):
    building: dict
    version: str = "IFC2X3"


@app.post("/api/v1/ifc/generate")
async def generate_ifc_endpoint(req: GenerateIFCRequest):
    """Generate IFC file from Building model."""
    output_path = generate_ifc(req.building, req.version)
    return FileResponse(
        output_path,
        media_type="application/x-step",
        filename=os.path.basename(output_path)
    )


@app.post("/api/v1/ifc/parse")
async def parse_ifc_endpoint(file: UploadFile = File(...)):
    """Parse uploaded IFC file."""
    # Save uploaded file
    job_id = uuid.uuid4().hex[:8]
    temp_path = os.path.join(OUTPUT_DIR, f"upload_{job_id}.ifc")

    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        result = parse_ifc(temp_path)
        return result
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


class ConvertRequest(BaseModel):
    building: dict
    target_format: str = "ifc"  # "ifc", "ifc4"


@app.post("/api/v1/ifc/convert")
async def convert_to_ifc(req: ConvertRequest):
    """Convert Building model to IFC format."""
    version = "IFC4" if req.target_format == "ifc4" else "IFC2X3"
    output_path = generate_ifc(req.building, version)

    with open(output_path, "r") as f:
        ifc_content = f.read()

    return {
        "format": version,
        "content": ifc_content,
        "filename": os.path.basename(output_path),
    }


if __name__ == "__main__":
    import uvicorn
    print(f"IFC Service starting on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
