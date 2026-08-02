"""
shared/cad_builder.py — Parametric wall generation with window/door openings.

Uses OpenCascade (pythonocc-core / OCP) for precise boolean operations.
Falls back to simplified geometry if OCCT is unavailable.

This module does NOT replace cad-service — it provides a higher-level API
for the geometry agent to generate architectural walls with openings.

Usage:
    from shared.cad_builder import WallBuilder, WallOpening, BuildingBuilder

    builder = WallBuilder()
    wall = builder.create_wall(
        start=(0, 0), end=(10, 0),
        thickness=0.3, height=3.0,
        openings=[
            WallOpening("window", width=1.2, height=1.5, sill_height=0.9, offset=2.0),
            WallOpening("door", width=0.9, height=2.1, sill_height=0.0, offset=6.0),
        ]
    )
    builder.export_step(wall, "/app/output/wall.step")
"""

import logging
import math
import os
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger("archai.cad_builder")

# ═══════════════════════════════════════════════════════════════
# OCCT availability check
# ═══════════════════════════════════════════════════════════════

OCCT_AVAILABLE = False
try:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut  # noqa: F401
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform  # noqa: F401
    from OCP.BRepGProp import BRepGProp  # noqa: F401
    from OCP.BRepMesh import BRepMesh_IncrementalMesh  # noqa: F401
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: F401
    from OCP.gp import gp_Pnt, gp_Trsf, gp_Vec  # noqa: F401
    from OCP.GProp import GProp_GProps  # noqa: F401
    from OCP.IFSelect import IFSelect_RetDone  # noqa: F401
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer  # noqa: F401
    from OCP.StlAPI import StlAPI_Writer  # noqa: F401
    from OCP.TopoDS import TopoDS_Builder, TopoDS_Compound, TopoDS_Shape  # noqa: F401

    OCCT_AVAILABLE = True
    logger.info("[cad_builder] OpenCascade (OCCT) loaded successfully")
except ImportError as e:
    logger.warning("[cad_builder] OCCT not available (%s) — using fallback geometry", e)


# ═══════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════


@dataclass
class WallOpening:
    """Opening (window or door) in a wall."""

    opening_type: str  # "window" | "door" | "arch"
    width: float  # meters
    height: float  # meters
    sill_height: float = 0.9  # meters from floor (0 for doors)
    offset: float = 0.0  # meters from wall start along wall length
    frame_depth: float = 0.05  # frame depth into wall

    def __post_init__(self):
        if self.opening_type == "door":
            self.sill_height = 0.0


@dataclass
class WallSpec:
    """Specification for a single wall."""

    start: tuple[float, float]  # (x, y) start point
    end: tuple[float, float]  # (x, y) end point
    thickness: float = 0.3  # meters
    height: float = 3.0  # meters
    openings: list[WallOpening] = field(default_factory=list)
    material: str = "brick"
    load_bearing: bool = False

    @property
    def length(self) -> float:
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return math.sqrt(dx * dx + dy * dy)

    @property
    def angle(self) -> float:
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return math.atan2(dy, dx)


@dataclass
class RoomSpec:
    """Specification for a room (4 walls + floor + ceiling)."""

    name: str
    x: float  # center x
    y: float  # center y
    width: float  # x dimension
    depth: float  # y dimension
    height: float = 3.0
    wall_thickness: float = 0.2
    openings: list[WallOpening] = field(default_factory=list)  # applied to exterior walls
    material: str = "plaster"


@dataclass
class FloorSpec:
    """Specification for a building floor."""

    level: int  # 0 = ground, 1 = first, etc.
    height: float = 3.0
    rooms: list[RoomSpec] = field(default_factory=list)
    elevation: float = 0.0  # auto-calculated if not set


@dataclass
class BuildingSpec:
    """Full building specification for CAD generation."""

    name: str = "Building"
    floors: list[FloorSpec] = field(default_factory=list)
    total_width: float = 10.0
    total_length: float = 12.0
    wall_thickness: float = 0.3
    floor_thickness: float = 0.2
    roof_type: str = "flat"  # flat | gabled | hip
    material: str = "brick"


# ═══════════════════════════════════════════════════════════════
# WALL BUILDER (OCCT)
# ═══════════════════════════════════════════════════════════════


class WallBuilder:
    """
    Generates parametric walls with boolean-cut openings using OpenCascade.

    If OCCT is unavailable, falls back to bpy-script generation.
    """

    def __init__(self, output_dir: str | None = None):
        self._output_dir = output_dir or os.environ.get("OUTPUT_DIR", "/tmp/arch_output")
        os.makedirs(self._output_dir, exist_ok=True)

    def create_wall(self, spec: WallSpec) -> "TopoDS_Shape | None":
        """
        Create a wall with openings using OCCT boolean operations.

        Returns:
            OCCT Shape if available, None otherwise
        """
        if not OCCT_AVAILABLE:
            logger.warning("OCCT not available — cannot create wall geometry")
            return None

        # 1. Create base wall box
        wall_length = spec.length
        wall_shape = self._make_wall_box(wall_length, spec.thickness, spec.height)

        if not spec.openings:
            return wall_shape

        # 2. Cut openings
        result = wall_shape
        for opening in spec.openings:
            opening_shape = self._make_opening_box(opening, wall_length, spec.thickness, spec.height)
            if opening_shape:
                try:
                    result = BRepAlgoAPI_Cut(result, opening_shape).Shape()
                except Exception as e:
                    logger.warning("Boolean cut failed for opening: %s", e)

        return result

    def create_room(self, spec: RoomSpec) -> list[tuple["TopoDS_Shape", str]]:
        """
        Create 4 walls for a room.

        Returns:
            list of (shape, wall_label) tuples
        """
        walls = []
        hw = spec.width / 2
        hd = spec.depth / 2
        t = spec.wall_thickness

        # Wall definitions: (start, end, label)
        wall_defs = [
            ((-hw, -hd), (hw, -hd), "south"),
            ((hw, -hd), (hw, hd), "east"),
            ((hw, hd), (-hw, hd), "north"),
            ((-hw, hd), (-hw, -hd), "west"),
        ]

        # Distribute openings to exterior walls
        exterior_openings = [o for o in spec.openings if o.opening_type == "door"]
        window_openings = [o for o in spec.openings if o.opening_type == "window"]

        for i, (start, end, label) in enumerate(wall_defs):
            wall_openings = []

            # Put doors on south wall (first wall)
            if label == "south" and exterior_openings:
                wall_openings = exterior_openings

            # Distribute windows evenly
            if window_openings:
                # Assign windows to east/north/west walls
                wall_idx = i - 1  # skip south for windows
                if wall_idx >= 0 and wall_idx < len(window_openings):
                    wall_openings.append(window_openings[wall_idx])

            wall_spec = WallSpec(
                start=start,
                end=end,
                thickness=t,
                height=spec.height,
                openings=wall_openings,
                material=spec.material,
            )

            shape = self.create_wall(wall_spec)
            if shape:
                walls.append((shape, f"{spec.name}_{label}"))

        return walls

    def create_building(self, spec: BuildingSpec) -> "TopoDS_Shape | None":
        """
        Create full building from spec with floors and rooms.

        Returns:
            Compound shape or None
        """
        if not OCCT_AVAILABLE:
            return None

        builder = TopoDS_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)

        for floor_spec in spec.floors:
            elevation = floor_spec.elevation or (floor_spec.level * floor_spec.height)

            if floor_spec.rooms:
                # Generate rooms
                for room in floor_spec.rooms:
                    room_walls = self.create_room(room)
                    for shape, label in room_walls:
                        # Translate to position + elevation
                        positioned = self._translate(
                            shape,
                            room.x,
                            room.y,
                            elevation,
                        )
                        if positioned:
                            builder.Add(compound, positioned)
            else:
                # Generate simple box building
                box = BRepPrimAPI_MakeBox(
                    gp_Pnt(-spec.total_width / 2, -spec.total_length / 2, elevation),
                    spec.total_width,
                    spec.total_length,
                    floor_spec.height,
                ).Shape()
                builder.Add(compound, box)

            # Floor slab
            floor_slab = BRepPrimAPI_MakeBox(
                gp_Pnt(-spec.total_width / 2, -spec.total_length / 2, elevation - spec.floor_thickness),
                spec.total_width,
                spec.total_length,
                spec.floor_thickness,
            ).Shape()
            builder.Add(compound, floor_slab)

        return compound

    def export_step(self, shape, filepath: str) -> bool:
        """Export OCCT shape to STEP format."""
        if not OCCT_AVAILABLE or shape is None:
            return False
        try:
            writer = STEPControl_Writer()
            writer.Transfer(shape, STEPControl_AsIs)
            status = writer.Write(filepath)
            return status == IFSelect_RetDone
        except Exception as e:
            logger.error("STEP export failed: %s", e)
            return False

    def export_stl(self, shape, filepath: str, tolerance: float = 0.01) -> bool:
        """Export OCCT shape to STL format."""
        if not OCCT_AVAILABLE or shape is None:
            return False
        try:
            mesh = BRepMesh_IncrementalMesh(shape, tolerance)
            mesh.Perform()
            writer = StlAPI_Writer()
            writer.Write(filepath)
            return os.path.exists(filepath)
        except Exception as e:
            logger.error("STL export failed: %s", e)
            return False

    def analyze_shape(self, shape) -> dict:
        """Get shape properties: volume, area, center of mass."""
        if not OCCT_AVAILABLE or shape is None:
            return {"error": "OCCT not available"}

        props = GProp_GProps()
        BRepGProp.VolumeProperties(shape, props)
        volume = props.Mass()
        center = props.CentreOfMass()

        area_props = GProp_GProps()
        BRepGProp.SurfaceProperties(shape, area_props)
        area = area_props.Mass()

        return {
            "volume_m3": round(volume, 4),
            "area_m2": round(area, 4),
            "center_of_mass": {
                "x": round(center.X(), 4),
                "y": round(center.Y(), 4),
                "z": round(center.Z(), 4),
            },
        }

    # ── Internal helpers ──

    def _make_wall_box(self, length: float, thickness: float, height: float):
        """Create a simple wall box."""
        return BRepPrimAPI_MakeBox(
            gp_Pnt(0, -thickness / 2, 0),
            length,
            thickness,
            height,
        ).Shape()

    def _make_opening_box(self, opening: WallOpening, wall_length: float, wall_thickness: float, wall_height: float):
        """Create a box shape for a wall opening."""
        # Validate opening fits in wall
        if opening.offset + opening.width > wall_length:
            logger.warning(
                "Opening at offset %.2f + width %.2f exceeds wall length %.2f",
                opening.offset,
                opening.width,
                wall_length,
            )
            # Clamp
            opening.width = wall_length - opening.offset - 0.01

        if opening.width <= 0 or opening.height <= 0:
            return None

        # Make opening slightly larger than wall for clean boolean cut
        margin = 0.02  # 2cm margin for clean cut
        box = BRepPrimAPI_MakeBox(
            gp_Pnt(
                opening.offset,
                -(wall_thickness / 2 + margin),
                opening.sill_height,
            ),
            opening.width,
            wall_thickness + 2 * margin,
            opening.height,
        ).Shape()
        return box

    def _translate(self, shape, dx: float, dy: float, dz: float):
        """Translate a shape."""
        try:
            trsf = gp_Trsf()
            trsf.SetTranslation(gp_Vec(dx, dy, dz))
            return BRepBuilderAPI_Transform(shape, trsf).Shape()
        except Exception as e:
            logger.warning("Translation failed: %s", e)
            return shape


# ═══════════════════════════════════════════════════════════════
# BUILDING BUILDER — high-level API
# ═══════════════════════════════════════════════════════════════


class BuildingBuilder:
    """
    High-level API: params dict → CAD model.

    Compatible with existing orchestrator params format.
    """

    def __init__(self, output_dir: str | None = None):
        self.wall_builder = WallBuilder(output_dir=output_dir)

    def from_params(self, params: dict, building_params: dict) -> BuildingSpec:
        """
        Convert orchestrator params to BuildingSpec.

        Args:
            params: parsed params from LLM
            building_params: building params from router
        """
        floors = building_params.get("floors", 2)
        width = building_params.get("W", 10)
        length = building_params.get("L", 12)
        floor_height = building_params.get("fH", 2.8)
        rooms_data = building_params.get("rooms", [])
        material = building_params.get("mat", "brick")

        floor_specs = []
        for fl in range(floors):
            fl_rooms = [r for r in rooms_data if r.get("fl") == fl + 1]
            room_specs = []
            for r in fl_rooms:
                room_specs.append(
                    RoomSpec(
                        name=r.get("n", f"Room {fl + 1}"),
                        x=r.get("x", 0),
                        y=r.get("z", 0),
                        width=r.get("w", 4),
                        depth=r.get("d", 4),
                        height=floor_height,
                        wall_thickness=0.2,
                        material=material,
                    )
                )

            floor_specs.append(
                FloorSpec(
                    level=fl,
                    height=floor_height,
                    rooms=room_specs,
                )
            )

        return BuildingSpec(
            name=building_params.get("desc", "Building")[:50],
            floors=floor_specs,
            total_width=width,
            total_length=length,
            wall_thickness=building_params.get("wall_thickness", 0.3),
            material=material,
        )

    def generate(self, params: dict, building_params: dict) -> dict:
        """
        Full generation pipeline: params → CAD model → export.

        Returns:
            {
                "spec": BuildingSpec,
                "step_path": "...",
                "stl_path": "...",
                "analysis": {...},
                "occt_available": bool,
            }
        """
        spec = self.from_params(params, building_params)
        job_id = uuid.uuid4().hex[:8]
        output_dir = self.wall_builder._output_dir

        result = {
            "spec": {
                "name": spec.name,
                "floors": len(spec.floors),
                "total_width": spec.total_width,
                "total_length": spec.total_length,
                "material": spec.material,
            },
            "step_path": None,
            "stl_path": None,
            "analysis": None,
            "occt_available": OCCT_AVAILABLE,
        }

        if not OCCT_AVAILABLE:
            result["note"] = "OCCT not available — CAD model not generated. Install pythonocc-core."
            return result

        # Generate building shape
        shape = self.wall_builder.create_building(spec)
        if shape is None:
            result["error"] = "Failed to create building geometry"
            return result

        # Export
        step_path = os.path.join(output_dir, f"building_{job_id}.step")
        stl_path = os.path.join(output_dir, f"building_{job_id}.stl")

        if self.wall_builder.export_step(shape, step_path):
            result["step_path"] = step_path

        if self.wall_builder.export_stl(shape, stl_path):
            result["stl_path"] = stl_path

        result["analysis"] = self.wall_builder.analyze_shape(shape)

        return result


# ═══════════════════════════════════════════════════════════════
# BPY SCRIPT FALLBACK — for when OCCT is unavailable
# ═══════════════════════════════════════════════════════════════


def generate_parametric_wall_bpy(
    start: tuple[float, float],
    end: tuple[float, float],
    thickness: float,
    height: float,
    openings: list[WallOpening],
) -> str:
    """
    Generate a bpy script for a wall with openings using Blender boolean modifier.

    This is the FALLBACK when OCCT is not available.
    Uses Blender's boolean modifier for CSG operations.
    """
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.sqrt(dx * dx + dy * dy)
    angle = math.atan2(dy, dx)

    cx = (start[0] + end[0]) / 2
    cy = (start[1] + end[1]) / 2
    cz = height / 2

    # Sanitize
    def _s(v):
        return round(v, 4)

    script_parts = []

    # Create wall mesh
    script_parts.append(f"""
# Parametric wall: {start} → {end}
import bpy, bmesh, math

# Clear existing
bpy.ops.object.select_all(action='DESELECT')

# Wall body
bpy.ops.mesh.primitive_cube_add(size=1, location=({_s(cx)}, {_s(cy)}, {_s(cz)}))
wall = bpy.context.active_object
wall.name = "ParamWall"
wall.scale = ({_s(length)}, {_s(thickness)}, {_s(height)})
wall.rotation_euler.z = {_s(angle)}
bpy.ops.object.transform_apply(scale=True, rotation=True)
""")

    # Create opening cutouts
    for i, opening in enumerate(openings):
        ox = start[0] + (end[0] - start[0]) * (opening.offset / length)
        oy = start[1] + (end[1] - start[1]) * (opening.offset / length)
        oz = opening.sill_height + opening.height / 2

        script_parts.append(f"""
# Opening {i}: {opening.opening_type}
bpy.ops.mesh.primitive_cube_add(size=1, location=({_s(ox)}, {_s(oy)}, {_s(oz)}))
opening_{i} = bpy.context.active_object
opening_{i}.name = "Opening_{i}_{opening.opening_type}"
opening_{i}.scale = ({_s(opening.width)}, {_s(thickness + 0.04)}, {_s(opening.height)})
opening_{i}.rotation_euler.z = {_s(angle)}
bpy.ops.object.transform_apply(scale=True, rotation=True)

# Boolean cut
wall.select_set(True)
bpy.context.view_layer.objects.active = wall
mod = wall.modifiers.new(name="Cut_{i}", type='BOOLEAN')
mod.operation = 'DIFFERENCE'
mod.object = opening_{i}
bpy.ops.object.modifier_apply(modifier="Cut_{i}")
bpy.data.objects.remove(opening_{i}, do_unlink=True)
""")

    return "\n".join(script_parts)


def generate_building_from_params_bpy(params: dict, building_params: dict) -> str:
    """
    Generate full building bpy script with parametric walls.

    Compatible with existing geometry agent interface.
    """
    builder = BuildingBuilder()
    spec = builder.from_params(params, building_params)

    scripts = []

    for floor in spec.floors:
        elevation = floor.elevation or (floor.level * floor.height)

        for room in floor.rooms:
            hw = room.width / 2
            hd = room.depth / 2
            t = room.wall_thickness

            # 4 walls
            wall_defs = [
                ((room.x - hw, room.y - hd), (room.x + hw, room.y - hd)),  # south
                ((room.x + hw, room.y - hd), (room.x + hw, room.y + hd)),  # east
                ((room.x + hw, room.y + hd), (room.x - hw, room.y + hd)),  # north
                ((room.x - hw, room.y + hd), (room.x - hw, room.y - hd)),  # west
            ]

            for j, (ws, we) in enumerate(wall_defs):
                openings = []
                # Add window to east/west/north walls
                if j > 0 and room.openings:
                    window_openings = [o for o in room.openings if o.opening_type == "window"]
                    if window_openings:
                        openings = [window_openings[0] if j - 1 < len(window_openings) else window_openings[-1]]

                # Add door to south wall
                if j == 0 and room.openings:
                    door_openings = [o for o in room.openings if o.opening_type == "door"]
                    if door_openings:
                        openings = door_openings

                wall_script = generate_parametric_wall_bpy(
                    start=(ws[0], ws[1]),
                    end=(we[0], we[1]),
                    thickness=t,
                    height=room.height,
                    openings=openings,
                )
                # Offset z by elevation
                wall_script = wall_script.replace(
                    f"location=({round((ws[0] + we[0]) / 2, 4)}, {round((ws[1] + we[1]) / 2, 4)}, {round(room.height / 2, 4)})",
                    f"location=({round((ws[0] + we[0]) / 2, 4)}, {round((ws[1] + we[1]) / 2, 4)}, {round(elevation + room.height / 2, 4)})",
                )
                scripts.append(wall_script)

    return "\n".join(scripts)
