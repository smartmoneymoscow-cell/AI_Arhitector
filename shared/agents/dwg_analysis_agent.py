"""
shared/agents/dwg_analysis_agent.py — DWG/DXF file analysis agent.

Parses DXF files using ezdxf library to extract:
- Layers, blocks, dimensions, text annotations
- Architectural elements by layer names
- Structured JSON output
"""

import logging
import os
from dataclasses import dataclass, field

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger("archai.dwg_analysis")


@dataclass
class LayerInfo:
    """Information about a DXF layer."""

    name: str = ""
    color: int = 0
    linetype: str = ""
    entity_count: int = 0
    is_architectural: bool = False
    element_type: str = ""  # wall, door, window, furniture, mep, dimension, text


@dataclass
class BlockInfo:
    """Information about a DXF block."""

    name: str = ""
    base_point: tuple = (0, 0, 0)
    entity_count: int = 0
    element_type: str = ""


@dataclass
class DimensionInfo:
    """Extracted dimension from DXF."""

    value: float = 0.0
    text: str = ""
    start: tuple = (0, 0)
    end: tuple = (0, 0)
    layer: str = ""


@dataclass
class DWGAnalysisResult:
    """Structured result from DWG/DXF analysis."""

    file_name: str = ""
    file_format: str = ""  # dxf or dwg
    layers: list[LayerInfo] = field(default_factory=list)
    blocks: list[BlockInfo] = field(default_factory=list)
    dimensions: list[DimensionInfo] = field(default_factory=list)
    text_annotations: list[str] = field(default_factory=list)
    entity_summary: dict = field(default_factory=dict)
    architectural_elements: dict = field(default_factory=dict)
    bounding_box: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "file_format": self.file_format,
            "layers": [
                {
                    "name": l.name,
                    "color": l.color,
                    "linetype": l.linetype,
                    "entity_count": l.entity_count,
                    "is_architectural": l.is_architectural,
                    "element_type": l.element_type,
                }
                for l in self.layers
            ],
            "blocks": [
                {
                    "name": b.name,
                    "base_point": list(b.base_point),
                    "entity_count": b.entity_count,
                    "element_type": b.element_type,
                }
                for b in self.blocks
            ],
            "dimensions": [
                {
                    "value": d.value,
                    "text": d.text,
                    "start": list(d.start),
                    "end": list(d.end),
                    "layer": d.layer,
                }
                for d in self.dimensions[:100]  # Limit to 100
            ],
            "text_annotations": self.text_annotations[:200],
            "entity_summary": self.entity_summary,
            "architectural_elements": self.architectural_elements,
            "bounding_box": self.bounding_box,
            "warnings": self.warnings,
        }


# Architectural layer name patterns (common conventions)
_ARCH_LAYER_PATTERNS = {
    "wall": ["wall", "стен", "walls", "a-wall", "arch-wall", "s_wall"],
    "door": ["door", "двер", "doors", "a-door", "d-"],
    "window": ["window", "окон", "windows", "a-window", "w-", "glazing"],
    "furniture": ["furniture", "мебел", "furn", "a-furn", "equip"],
    "mep": ["mep", "hvac", "вентил", "отопл", "водопровод", "канализац", "электр", "plumbing", "mechanical"],
    "dimension": ["dim", "размер", "dimension", "标注", "annotation"],
    "text": ["text", "текст", "label", "note", "anno"],
    "structure": ["struct", "конструкт", "column", "колонн", "beam", "балк", "foundation", "фундам"],
    "stairs": ["stair", "лестниц", "elevator", "лифт"],
    "roof": ["roof", "кровл", "крыш"],
    "floor": ["floor", "пол", "перекрыт", "slab"],
    "ceiling": ["ceiling", "потолок"],
    "site": ["site", "territory", "участок", "landscape", "ландшафт"],
}


def _classify_layer(name: str) -> tuple[bool, str]:
    """Classify a layer as architectural and determine element type."""
    name_lower = name.lower().strip()
    for element_type, patterns in _ARCH_LAYER_PATTERNS.items():
        for pattern in patterns:
            if pattern in name_lower:
                return True, element_type
    return False, ""


def _extract_entity_summary(doc) -> dict:
    """Count entities by type."""
    summary = {}
    try:
        for entity in doc.modelspace():
            etype = entity.dxftype()
            summary[etype] = summary.get(etype, 0) + 1
    except Exception as e:
        logger.warning("Error counting entities: %s", e)
    return summary


def _extract_dimensions(doc) -> list[DimensionInfo]:
    """Extract dimension entities."""
    dims = []
    try:
        msp = doc.modelspace()
        for entity in msp.query("DIMENSION"):
            try:
                d = DimensionInfo(
                    text=entity.dxf.text if hasattr(entity.dxf, "text") else "",
                    layer=entity.dxf.layer if hasattr(entity.dxf, "layer") else "",
                )
                # Try to get measurement value
                if hasattr(entity, "measurement"):
                    try:
                        d.value = float(entity.measurement)
                    except (TypeError, ValueError):
                        pass
                dims.append(d)
            except Exception:
                continue
    except Exception as e:
        logger.warning("Error extracting dimensions: %s", e)
    return dims


def _extract_text_annotations(doc) -> list[str]:
    """Extract text and mtext entities."""
    texts = []
    try:
        msp = doc.modelspace()
        for entity in msp.query("TEXT MTEXT"):
            try:
                if entity.dxftype() == "TEXT":
                    text = entity.dxf.text
                else:
                    text = entity.text
                if text and text.strip():
                    texts.append(text.strip()[:500])
            except Exception:
                continue
    except Exception as e:
        logger.warning("Error extracting text: %s", e)
    return texts


def analyze_dxf(file_path: str) -> DWGAnalysisResult:
    """
    Analyze a DXF file and extract architectural information.

    Args:
        file_path: Path to the DXF file

    Returns:
        DWGAnalysisResult with structured data
    """
    result = DWGAnalysisResult()

    if not os.path.exists(file_path):
        result.warnings.append(f"File not found: {file_path}")
        return result

    result.file_name = os.path.basename(file_path)
    result.file_format = "dxf" if file_path.lower().endswith(".dxf") else "dwg"

    try:
        import ezdxf

        doc = ezdxf.readfile(file_path)
        msp = doc.modelspace()

        # Extract layers
        for layer in doc.layers:
            is_arch, element_type = _classify_layer(layer.dxf.name)
            entity_count = 0
            try:
                entity_count = len(list(msp.query(f'*[layer=="{layer.dxf.name}"]')))
            except Exception:
                pass

            result.layers.append(
                LayerInfo(
                    name=layer.dxf.name,
                    color=layer.dxf.color if hasattr(layer.dxf, "color") else 0,
                    linetype=layer.dxf.linetype if hasattr(layer.dxf, "linetype") else "",
                    entity_count=entity_count,
                    is_architectural=is_arch,
                    element_type=element_type,
                )
            )

        # Extract blocks
        for block in doc.blocks:
            if not block.name.startswith("*"):  # Skip anonymous blocks
                entity_count = len(list(block))
                base = (0, 0, 0)
                if hasattr(block, "base_point"):
                    base = tuple(block.base_point)
                is_arch, element_type = _classify_layer(block.name)
                result.blocks.append(
                    BlockInfo(
                        name=block.name,
                        base_point=base,
                        entity_count=entity_count,
                        element_type=element_type,
                    )
                )

        # Extract dimensions
        result.dimensions = _extract_dimensions(doc)

        # Extract text annotations
        result.text_annotations = _extract_text_annotations(doc)

        # Entity summary
        result.entity_summary = _extract_entity_summary(doc)

        # Architectural elements summary
        arch_elements = {}
        for layer in result.layers:
            if layer.is_architectural:
                if layer.element_type not in arch_elements:
                    arch_elements[layer.element_type] = {"layers": [], "total_entities": 0}
                arch_elements[layer.element_type]["layers"].append(layer.name)
                arch_elements[layer.element_type]["total_entities"] += layer.entity_count
        result.architectural_elements = arch_elements

        # Bounding box
        try:
            extents = msp.extents()
            if extents:
                result.bounding_box = {
                    "min_x": round(extents.extmin[0], 3),
                    "min_y": round(extents.extmin[1], 3),
                    "max_x": round(extents.extmax[0], 3),
                    "max_y": round(extents.extmax[1], 3),
                    "width": round(extents.extmax[0] - extents.extmin[0], 3),
                    "height": round(extents.extmax[1] - extents.extmin[1], 3),
                }
        except Exception:
            pass

    except ImportError:
        result.warnings.append("ezdxf library not installed — DXF parsing unavailable")
        logger.warning("ezdxf not installed")
    except Exception as e:
        result.warnings.append(f"DXF analysis error: {str(e)}")
        logger.error("DXF analysis failed: %s", e, exc_info=True)

    return result


def convert_dwg_to_dxf(dwg_path: str) -> str:
    """
    Convert DWG to DXF using ODA File Converter (if available).
    Returns path to converted DXF file.
    """
    import subprocess
    import tempfile

    output_dir = tempfile.mkdtemp()
    output_path = os.path.join(output_dir, os.path.splitext(os.path.basename(dwg_path))[0] + ".dxf")

    try:
        # Try ODA File Converter
        result = subprocess.run(
            ["ODAFileConverter", os.path.dirname(dwg_path), output_dir, "ACAD2018", "DXF", "0", "1"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Try LibreCAD converter as fallback
    try:
        result = subprocess.run(
            ["librecad", "-dxf", dwg_path, output_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return ""


class DWGAnalysisAgent(BaseAgent):
    """Agent for analyzing uploaded DWG/DXF files."""

    name = "dwg_analysis"

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

            # If DWG, try to convert to DXF first
            if file_path.lower().endswith(".dwg"):
                dxf_path = convert_dwg_to_dxf(file_path)
                if dxf_path:
                    file_path = dxf_path
                else:
                    return TaskResult(
                        status=TaskStatus.FAILED,
                        error="Cannot convert DWG to DXF. Install ODA File Converter.",
                        duration_ms=(__import__("time").time() - start) * 1000,
                    )

            result = analyze_dxf(file_path)

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
