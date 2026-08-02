"""
Shared BIM Data Models — Pydantic schemas for all services.

Used for:
  - Inter-service communication
  - API request/response validation
  - BIM data serialization
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
import uuid


# ═══════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════

class ObjectType(str, Enum):
    BUILDING = "building"
    ROOM = "room"
    INTERIOR = "interior"
    LANDSCAPE = "landscape"
    STRUCTURE = "structure"


class BuildingType(str, Enum):
    HOUSE = "house"
    OFFICE = "office"
    COTTAGE = "cottage"
    VILLA = "villa"
    APARTMENT = "apartment"
    TOWNHOUSE = "townhouse"
    HOTEL = "hotel"
    SCHOOL = "school"
    HOSPITAL = "hospital"


class RoomType(str, Enum):
    BEDROOM = "bedroom"
    KITCHEN = "kitchen"
    LIVING = "living"
    BATHROOM = "bathroom"
    CHILDREN = "children"
    STUDY = "study"
    DINING = "dining"
    HALLWAY = "hallway"
    BALCONY = "balcony"
    GARAGE = "garage"


class Style(str, Enum):
    MODERN = "modern"
    CLASSIC = "classic"
    LOFT = "loft"
    SCANDINAVIAN = "scandinavian"
    MINIMALIST = "minimalist"
    HITECH = "hitech"
    BAROQUE = "baroque"
    CONSTRUCTIVISM = "constructivism"


class Material(str, Enum):
    BRICK = "brick"
    WOOD = "wood"
    GLASS = "glass"
    STONE = "stone"
    CONCRETE = "concrete"
    PLASTER = "plaster"
    METAL = "metal"
    COMPOSITE = "composite"


class RoofType(str, Enum):
    GABLED = "gabled"
    FLAT = "flat"
    HIP = "hip"
    MANSARD = "mansard"
    DOME = "dome"


# ═══════════════════════════════════════════════════════════════
# GEOMETRY PRIMITIVES
# ═══════════════════════════════════════════════════════════════

class Point2D(BaseModel):
    x: float
    y: float


class Point3D(BaseModel):
    x: float
    y: float
    z: float = 0.0


class BBox(BaseModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def area(self) -> float:
        return self.width * self.height


class Polygon2D(BaseModel):
    """2D polygon (floor plan, wall, etc.)"""
    points: List[Point2D]
    holes: List[List[Point2D]] = []

    def to_wkt(self) -> str:
        exterior = ",".join(f"{p.x} {p.y}" for p in self.points)
        if not self.holes:
            return f"POLYGON(({exterior}))"
        holes = ",".join(
            "(" + ",".join(f"{p.x} {p.y}" for p in hole) + ")"
            for hole in self.holes
        )
        return f"POLYGON(({exterior}),{holes})"


# ═══════════════════════════════════════════════════════════════
# BIM ELEMENTS
# ═══════════════════════════════════════════════════════════════

class Wall(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    start: Point2D
    end: Point2D
    thickness: float = 0.3
    height: float = 3.0
    material: Material = Material.BRICK
    is_load_bearing: bool = False
    is_exterior: bool = True


class Window(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    wall_id: str
    position: Point2D  # center on wall
    width: float = 1.2
    height: float = 1.5
    sill_height: float = 0.9


class Door(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    wall_id: str
    position: Point2D
    width: float = 0.9
    height: float = 2.1
    is_exterior: bool = True


class Slab(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    polygon: Polygon2D
    thickness: float = 0.2
    elevation: float = 0.0
    material: Material = Material.CONCRETE


class Roof(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    polygon: Polygon2D
    roof_type: RoofType = RoofType.GABLED
    ridge_height: float = 2.5
    overhang: float = 0.3
    material: Material = Material.WOOD


class Column(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    position: Point2D
    width: float = 0.4
    depth: float = 0.4
    height: float = 3.0
    material: Material = Material.CONCRETE


class Furniture(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str
    category: str  # "sofa", "table", "bed", etc.
    position: Point3D
    rotation: float = 0.0  # degrees
    width: float = 1.0
    depth: float = 1.0
    height: float = 0.8
    material_color: str = "#888888"


# ═══════════════════════════════════════════════════════════════
# ROOM & BUILDING
# ═══════════════════════════════════════════════════════════════

class Room(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    room_type: RoomType = RoomType.LIVING
    polygon: Polygon2D
    floor: int = 0
    height: float = 3.0
    walls: List[Wall] = []
    doors: List[Door] = []
    windows: List[Window] = []
    furniture: List[Furniture] = []
    area: float = 0.0  # computed


class Floor(BaseModel):
    level: int = 0
    elevation: float = 0.0
    height: float = 3.0
    rooms: List[Room] = []
    slab: Optional[Slab] = None
    total_area: float = 0.0


class Building(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "Building"
    building_type: BuildingType = BuildingType.HOUSE
    style: Style = Style.MODERN
    floors: List[Floor] = []
    roof: Optional[Roof] = None
    columns: List[Column] = []
    footprint: Optional[Polygon2D] = None
    total_area: float = 0.0
    total_height: float = 0.0

    # Materials
    facade_material: Material = Material.PLASTER
    facade_color: Optional[str] = None

    # Features
    has_balcony: bool = False
    has_terrace: bool = False
    has_garage: bool = False
    has_basement: bool = False

    # Metadata
    address: Optional[str] = None
    coordinates: Optional[Point2D] = None  # lat/lon
    author: Optional[str] = None
    created_at: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# API MODELS
# ═══════════════════════════════════════════════════════════════

class GenerateRequest(BaseModel):
    prompt: str
    object_type: Optional[ObjectType] = None
    building_type: BuildingType = BuildingType.HOUSE
    room_type: Optional[RoomType] = None
    floors: int = Field(2, ge=1, le=50)
    width_m: float = Field(10, ge=1, le=500)
    length_m: float = Field(12, ge=1, le=500)
    height_m: float = Field(3, ge=1, le=20)
    style: Style = Style.MODERN
    material: Material = Material.PLASTER
    roof_type: RoofType = RoofType.GABLED
    features: List[str] = []
    furniture: List[str] = []

    # Advanced
    lot_width: Optional[float] = None
    lot_length: Optional[float] = None
    setback_front: float = 5.0
    setback_side: float = 3.0
    setback_back: float = 5.0
    max_coverage: float = 0.4  # 40% of lot


class AnalyzeRequest(BaseModel):
    """Request for spatial analysis"""
    building_id: Optional[str] = None
    building: Optional[Building] = None
    analysis_type: str = "full"  # "full", "structural", "spatial", "energy"
    include_ifc: bool = False


class ExportRequest(BaseModel):
    building_id: Optional[str] = None
    building: Optional[Building] = None
    format: str = "ifc"  # "ifc", "gltf", "obj", "svg", "dxf"
    include_furniture: bool = True
    include_structure: bool = True


class AnalysisResult(BaseModel):
    total_area: float
    total_volume: float
    room_areas: Dict[str, float]
    wall_lengths: Dict[str, float]
    window_to_wall_ratio: float
    natural_light_score: float  # 0-100
    circulation_score: float  # 0-100
    structural_issues: List[str] = []
    recommendations: List[str] = []
    graph: Optional[Dict[str, Any]] = None  # NetworkX graph as JSON
