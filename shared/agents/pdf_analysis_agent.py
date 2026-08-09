"""
shared/agents/pdf_analysis_agent.py — PDF architectural drawing analysis agent.

Extracts structured data from uploaded PDF files:
- Text, dimensions, annotations
- Room names and areas
- Materials from specifications
- MEP systems (ventilation, heating, water, sewage)
"""

import logging
import os
import re
from dataclasses import dataclass, field

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger("archai.pdf_analysis")


@dataclass
class RoomInfo:
    """Extracted room information."""

    name: str = ""
    area_m2: float = 0.0
    width_m: float = 0.0
    length_m: float = 0.0
    floor: int = 1
    materials: list[str] = field(default_factory=list)


@dataclass
class MEPSystem:
    """Extracted MEP system information."""

    system_type: str = ""  # ventilation, heating, water_supply, sewage
    description: str = ""
    components: list[str] = field(default_factory=list)
    location: str = ""


@dataclass
class PDFAnalysisResult:
    """Structured result from PDF analysis."""

    file_name: str = ""
    page_count: int = 0
    rooms: list[RoomInfo] = field(default_factory=list)
    dimensions: dict = field(default_factory=dict)
    mep_systems: list[MEPSystem] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)
    drawing_type: str = ""  # floor_plan, section, elevation, specification
    raw_text: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "page_count": self.page_count,
            "rooms": [
                {
                    "name": r.name,
                    "area_m2": r.area_m2,
                    "width_m": r.width_m,
                    "length_m": r.length_m,
                    "floor": r.floor,
                    "materials": r.materials,
                }
                for r in self.rooms
            ],
            "dimensions": self.dimensions,
            "mep_systems": [
                {
                    "system_type": m.system_type,
                    "description": m.description,
                    "components": m.components,
                    "location": m.location,
                }
                for m in self.mep_systems
            ],
            "materials": self.materials,
            "annotations": self.annotations,
            "drawing_type": self.drawing_type,
            "warnings": self.warnings,
        }


def _extract_rooms(text: str) -> list[RoomInfo]:
    """Extract room names and dimensions from text."""
    rooms = []
    # Common room patterns in architectural drawings
    room_patterns = [
        # Russian: "Гостиная 5.4x3.8" or "Спальня 4.2x3.5 м"
        r"(?:Гостиная|Спальня|Кухня|Ванная|Туалет|Прихожая|Детская|Кабинет|Столовая|Коридор|Гардероб|Балкон|Терраса|Сауна|Котельная|Прачечная|Кладовая)\s*[:\-]?\s*(\d+[.,]\d*)\s*[xх×]\s*(\d+[.,]\d*)",
        # English: "Living Room 5.4x3.8"
        r"(?:Living\s*Room|Bedroom|Kitchen|Bathroom|Toilet|Hallway|Children|Study|Dining|Corridor|Wardrobe|Balcony|Terrace|Sauna|Boiler|Laundry|Pantry)\s*[:\-]?\s*(\d+[.,]\d*)\s*[xх×]\s*(\d+[.,]\d*)",
        # Generic: "Помещение 1 (жилая) 5.4x3.8"
        r"(?:Помещение|Room)\s*\d+\s*\([^)]*\)\s*(\d+[.,]\d*)\s*[xх×]\s*(\d+[.,]\d*)",
    ]

    # Room name extraction patterns
    name_patterns = [
        r"(Гостиная|Спальня|Кухня|Ванная|Туалет|Прихожая|Детская|Кабинет|Столовая|Коридор|Гардероб|Балкон|Терраса|Сауна|Котельная|Прачечная|Кладовая)",
        r"(Living\s*Room|Bedroom|Kitchen|Bathroom|Toilet|Hallway|Children|Study|Dining|Corridor|Wardrobe|Balcony|Terrace|Sauna|Boiler|Laundry|Pantry)",
    ]

    for pattern in room_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            w = float(match.group(1).replace(",", "."))
            l = float(match.group(2).replace(",", "."))
            room = RoomInfo(width_m=w, length_m=l, area_m2=round(w * l, 2))

            # Try to find the room name before the dimensions
            start = match.start()
            preceding = text[max(0, start - 50) : start]
            for np in name_patterns:
                nm = re.search(np, preceding, re.IGNORECASE)
                if nm:
                    room.name = nm.group(1).strip()
                    break

            if not room.name:
                room.name = f"Room {len(rooms) + 1}"
            rooms.append(room)

    # Also extract room names without dimensions
    for np in name_patterns:
        for match in re.finditer(np, text, re.IGNORECASE):
            name = match.group(1).strip()
            if not any(r.name.lower() == name.lower() for r in rooms):
                rooms.append(RoomInfo(name=name))

    return rooms


def _extract_dimensions(text: str) -> dict:
    """Extract overall building dimensions."""
    dims = {}

    # Building dimensions: "10x12", "10×12 м", "10.5 x 12.3"
    m = re.search(r"(\d+[.,]?\d*)\s*[xх×]\s*(\d+[.,]?\d*)\s*(?:м|m)?", text)
    if m:
        dims["width_m"] = float(m.group(1).replace(",", "."))
        dims["length_m"] = float(m.group(2).replace(",", "."))

    # Total area: "S=120 м²", "Площадь: 120 кв.м"
    m = re.search(r"(?:S|Площадь|Area)[:\s=]*(\d+[.,]?\d*)\s*(?:м²|м2|кв\.?м|m²|m2)", text, re.IGNORECASE)
    if m:
        dims["total_area_m2"] = float(m.group(1).replace(",", "."))

    # Floor height: "h=3.0", "Высота: 3.0 м"
    m = re.search(r"(?:h|Высота|Height)[:\s=]*(\d+[.,]?\d*)\s*(?:м|m)?", text, re.IGNORECASE)
    if m:
        dims["floor_height_m"] = float(m.group(1).replace(",", "."))

    # Floors: "3 этажа", "Этажность: 3"
    m = re.search(r"(\d+)\s*(?:этаж|floor|storey)", text, re.IGNORECASE)
    if m:
        dims["floors"] = int(m.group(1))

    return dims


def _extract_mep_systems(text: str) -> list[MEPSystem]:
    """Extract MEP (mechanical/electrical/plumbing) systems."""
    systems = []

    # Ventilation
    vent_keywords = ["вентиляц", "ventilation", "вытяжк", "приток", "air handling", "AHU"]
    if any(kw in text.lower() for kw in vent_keywords):
        system = MEPSystem(system_type="ventilation", description="Ventilation system detected")
        for kw in ["вытяжк", "приточн", "рекуперац", "канал", "duct", "exhaust", "supply"]:
            if kw in text.lower():
                system.components.append(kw)
        systems.append(system)

    # Heating
    heat_keywords = ["отоплен", "heating", "радиатор", "тёплый пол", "котёл", "boiler", "radiator"]
    if any(kw in text.lower() for kw in heat_keywords):
        system = MEPSystem(system_type="heating", description="Heating system detected")
        for kw in ["радиатор", "тёплый пол", "котёл", "стояк", "radiator", "underfloor", "boiler"]:
            if kw in text.lower():
                system.components.append(kw)
        systems.append(system)

    # Water supply
    water_keywords = ["водоснабжен", "water supply", "холодная вода", "горячая вода", "ХВС", "ГВС"]
    if any(kw in text.lower() for kw in water_keywords):
        system = MEPSystem(system_type="water_supply", description="Water supply system detected")
        for kw in ["стояк", "ввод", "счётчик", "коллектор", "riser", "meter"]:
            if kw in text.lower():
                system.components.append(kw)
        systems.append(system)

    # Sewage
    sewage_keywords = ["канализац", "sewage", "drainage", "сток", "канализацион"]
    if any(kw in text.lower() for kw in sewage_keywords):
        system = MEPSystem(system_type="sewage", description="Sewage system detected")
        for kw in ["стояк", "выпуск", "труб", "канал", "riser", "pipe"]:
            if kw in text.lower():
                system.components.append(kw)
        systems.append(system)

    # Electrical
    elec_keywords = ["электрич", "electrical", "освещен", "lighting", "щит", "panel", "розетк", "socket"]
    if any(kw in text.lower() for kw in elec_keywords):
        system = MEPSystem(system_type="electrical", description="Electrical system detected")
        for kw in ["щит", "розетк", "выключат", "светильник", "panel", "socket", "switch", "light"]:
            if kw in text.lower():
                system.components.append(kw)
        systems.append(system)

    return systems


def _extract_materials(text: str) -> list[str]:
    """Extract materials from specifications."""
    materials = []
    material_keywords = {
        "кирпич": "brick", "бетон": "concrete", "дерево": "wood", "сталь": "steel",
        "стекло": "glass", "гипсокартон": "drywall", "штукатурк": "plaster",
        "керамогранит": "porcelain_tile", "ламинат": "laminate", "паркет": "parquet",
        "мрамор": "marble", "гранит": "granite", "ПВХ": "PVC", "минвата": "mineral_wool",
        "пенобетон": "foam_concrete", "газобетон": "aerated_concrete", "CLT": "CLT",
        "brick": "brick", "concrete": "concrete", "wood": "wood", "steel": "steel",
        "glass": "glass", "drywall": "drywall", "plaster": "plaster",
        "tile": "tile", "marble": "marble", "granite": "granite",
    }
    text_lower = text.lower()
    for keyword, material in material_keywords.items():
        if keyword in text_lower and material not in materials:
            materials.append(material)
    return materials


def _detect_drawing_type(text: str) -> str:
    """Detect the type of architectural drawing."""
    text_lower = text.lower()
    if any(kw in text_lower for kw in ["этаж", "plan", "план", "планировк"]):
        return "floor_plan"
    if any(kw in text_lower for kw in ["разрез", "section", "сечени"]):
        return "section"
    if any(kw in text_lower for kw in ["фасад", "elevation", "facade"]):
        return "elevation"
    if any(kw in text_lower for kw in ["спецификац", "specification", "ведомость", "spec"]):
        return "specification"
    if any(kw in text_lower for kw in ["схема", "diagram", "axonometр"]):
        return "diagram"
    return "unknown"


def analyze_pdf(file_path: str) -> PDFAnalysisResult:
    """
    Analyze a PDF file and extract architectural information.

    Args:
        file_path: Path to the PDF file

    Returns:
        PDFAnalysisResult with structured data
    """
    result = PDFAnalysisResult()

    if not os.path.exists(file_path):
        result.warnings.append(f"File not found: {file_path}")
        return result

    result.file_name = os.path.basename(file_path)

    try:
        import fitz  # PyMuPDF

        doc = fitz.open(file_path)
        result.page_count = len(doc)

        full_text = ""
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            full_text += text + "\n"

            # Extract annotations
            for annot in page.annots() or []:
                if annot.info and annot.info.get("content"):
                    result.annotations.append(annot.info["content"])

            # Extract dimensions from page
            # PyMuPDF can extract text with position info
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block.get("type") == 0:  # text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            span_text = span.get("text", "")
                            # Look for dimension text (usually in specific fonts or sizes)
                            if re.search(r"\d+[.,]?\d*\s*[xх×]\s*\d+[.,]?\d*", span_text):
                                result.annotations.append(f"Dimension: {span_text}")

        doc.close()

        result.raw_text = full_text[:5000]  # Keep first 5000 chars for reference

        # Extract structured data
        result.rooms = _extract_rooms(full_text)
        result.dimensions = _extract_dimensions(full_text)
        result.mep_systems = _extract_mep_systems(full_text)
        result.materials = _extract_materials(full_text)
        result.drawing_type = _detect_drawing_type(full_text)

        if not result.rooms:
            result.warnings.append("No rooms detected in PDF text")
        if not result.dimensions:
            result.warnings.append("No building dimensions detected")

    except ImportError:
        result.warnings.append("PyMuPDF (fitz) not installed — PDF text extraction unavailable")
        logger.warning("PyMuPDF not installed")
    except Exception as e:
        result.warnings.append(f"PDF analysis error: {str(e)}")
        logger.error("PDF analysis failed: %s", e, exc_info=True)

    return result


class PDFAnalysisAgent(BaseAgent):
    """Agent for analyzing uploaded PDF architectural drawings."""

    name = "pdf_analysis"

    def process(self, task: Task) -> TaskResult:
        start = __import__("time").time()
        try:
            file_path = task.params.get("file_path", "")
            if not file_path:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    error="No file_path provided",
                    duration_ms=0,
                )

            result = analyze_pdf(file_path)

            return TaskResult(
                status=TaskStatus.DONE,
                data=result.to_dict(),
                duration_ms=(__import__("time").time() - start) * 1000,
            )
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(__import__("time").time() - start) * 1000,
            )

# PEP 8 alias
PdfAnalysisAgent = PDFAnalysisAgent
