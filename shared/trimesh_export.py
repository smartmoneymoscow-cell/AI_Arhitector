"""
shared/trimesh_export.py — Fast GLB/DXF export via trimesh.

Provides lightweight 3D export without requiring Blender.
Uses trimesh library for mesh processing and export.

Faster than Blender for simple geometry (boxes, walls).
Used as alternative to Blender service for quick previews.

Usage:
    from shared.trimesh_export import TrimeshExporter

    exporter = TrimeshExporter()
    glb_path = exporter.export_box_to_glb(
        width=10, length=12, height=6,
        filepath="/app/output/building.glb"
    )
"""

import logging
import os
import uuid
from typing import Optional

logger = logging.getLogger("archai.trimesh_export")

# ═══════════════════════════════════════════════════════════════
# TRIMESH AVAILABILITY
# ═══════════════════════════════════════════════════════════════

TRIMESH_AVAILABLE = False
try:
    import trimesh
    import trimesh.creation
    import numpy as np

    TRIMESH_AVAILABLE = True
    logger.info("[trimesh_export] trimesh loaded successfully")
except ImportError as e:
    logger.warning("[trimesh_export] trimesh not available: %s", e)


class TrimeshExporter:
    """
    Fast 3D export using trimesh.

    Supports: GLB, GLTF, STL, PLY, OBJ, DXF, SVG.
    """

    def __init__(self, output_dir: str = "/app/output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def export_box_to_glb(
        self,
        width: float,
        length: float,
        height: float,
        filepath: Optional[str] = None,
        color: tuple[float, float, float, float] = (0.8, 0.8, 0.8, 1.0),
    ) -> Optional[str]:
        """
        Export a simple box to GLB.

        Args:
            width, length, height: dimensions in meters
            filepath: output path (auto-generated if None)
            color: RGBA color

        Returns:
            Path to GLB file or None
        """
        if not TRIMESH_AVAILABLE:
            logger.warning("trimesh not available — cannot export GLB")
            return None

        try:
            mesh = trimesh.creation.box(extents=[width, height, length])

            # Apply color
            mesh.visual = trimesh.visual.ColorVisuals(
                mesh,
                vertex_colors=np.array([color] * len(mesh.vertices), dtype=np.uint8),
            )

            if filepath is None:
                filepath = os.path.join(self.output_dir, f"box_{uuid.uuid4().hex[:8]}.glb")

            mesh.export(filepath, file_type="glb")
            logger.info("Exported box GLB: %s (%.1f KB)", filepath, os.path.getsize(filepath) / 1024)
            return filepath

        except Exception as e:
            logger.error("GLB export failed: %s", e)
            return None

    def export_building_to_glb(
        self,
        building_params: dict,
        filepath: Optional[str] = None,
    ) -> Optional[str]:
        """
        Export building geometry to GLB from params.

        Creates a simple mesh representation (boxes for walls, roof, etc.)
        Much faster than full Blender rendering.
        """
        if not TRIMESH_AVAILABLE:
            return None

        try:
            meshes = []
            width = building_params.get("W", 10)
            length = building_params.get("L", 12)
            floors = building_params.get("floors", 2)
            floor_height = building_params.get("fH", 2.8)
            wall_thickness = building_params.get("wall_thickness", 0.3)
            material = building_params.get("mat", "plaster")

            # Material colors
            COLORS = {
                "brick": (0.71, 0.40, 0.12, 1.0),
                "wood": (0.55, 0.41, 0.13, 1.0),
                "glass": (0.6, 0.8, 1.0, 0.5),
                "plaster": (0.91, 0.88, 0.83, 1.0),
                "stone": (0.5, 0.5, 0.5, 1.0),
                "concrete": (0.63, 0.63, 0.63, 1.0),
            }
            color = COLORS.get(material, COLORS["plaster"])

            total_height = floors * floor_height

            # Main building shell
            shell = trimesh.creation.box(extents=[width, total_height, length])
            shell.visual = trimesh.visual.ColorVisuals(
                shell, vertex_colors=np.array([color] * len(shell.vertices), dtype=np.uint8)
            )
            meshes.append(shell)

            # Interior walls (from rooms)
            rooms = building_params.get("rooms", [])
            for room in rooms:
                rx = room.get("x", 0)
                rz = room.get("z", 0)
                rw = room.get("w", 4)
                rd = room.get("d", 4)
                rfl = room.get("fl", 1)

                # Room box (slightly smaller, different shade)
                room_color = (
                    min(1, color[0] * 1.1),
                    min(1, color[1] * 1.1),
                    min(1, color[2] * 1.1),
                    1.0,
                )
                room_mesh = trimesh.creation.box(extents=[rw, floor_height * 0.95, rd])
                room_mesh.visual = trimesh.visual.ColorVisuals(
                    room_mesh, vertex_colors=np.array([room_color] * len(room_mesh.vertices), dtype=np.uint8)
                )
                # Position
                room_mesh.apply_translation([rx, (rfl - 0.5) * floor_height, rz])
                meshes.append(room_mesh)

            # Roof
            roof_type = building_params.get("roof", "flat")
            if roof_type == "gabled":
                # Simple triangular roof
                roof_height = 2.0
                roof_mesh = trimesh.creation.box(extents=[width + 0.5, roof_height, length + 0.5])
                roof_color = (0.4, 0.2, 0.1, 1.0)  # dark brown
                roof_mesh.visual = trimesh.visual.ColorVisuals(
                    roof_mesh, vertex_colors=np.array([roof_color] * len(roof_mesh.vertices), dtype=np.uint8)
                )
                roof_mesh.apply_translation([0, total_height + roof_height / 2, 0])
                meshes.append(roof_mesh)

            # Windows (as glass-colored thin boxes)
            glass_color = COLORS["glass"]
            for room in rooms:
                rfl = room.get("fl", 1)
                rx = room.get("x", 0)
                rz = room.get("z", 0)
                rw = room.get("w", 4)
                rd = room.get("d", 4)

                # Add a window on each exterior-facing room
                window = trimesh.creation.box(extents=[1.2, 1.4, 0.05])
                window.visual = trimesh.visual.ColorVisuals(
                    window, vertex_colors=np.array([glass_color] * len(window.vertices), dtype=np.uint8)
                )
                y_pos = (rfl - 0.5) * floor_height + 1.0
                # Place on front face
                window.apply_translation([rx, y_pos, rz - rd / 2 - 0.01])
                meshes.append(window)

            # Combine all meshes
            scene = trimesh.Scene(meshes)

            if filepath is None:
                filepath = os.path.join(self.output_dir, f"building_{uuid.uuid4().hex[:8]}.glb")

            scene.export(filepath)
            logger.info("Exported building GLB: %s (%.1f KB)", filepath, os.path.getsize(filepath) / 1024)
            return filepath

        except Exception as e:
            logger.error("Building GLB export failed: %s", e, exc_info=True)
            return None

    def export_floorplan_to_svg(
        self,
        building_params: dict,
        filepath: Optional[str] = None,
        scale: float = 50.0,  # pixels per meter
        show_dimensions: bool = True,
        show_room_names: bool = True,
    ) -> Optional[str]:
        """
        Export floor plan to SVG with dimensions.

        Lightweight alternative to drawings_svg module.
        """
        try:
            width = building_params.get("W", 10)
            length = building_params.get("L", 12)
            rooms = building_params.get("rooms", [])
            wall_thickness = building_params.get("wall_thickness", 0.3)

            svg_w = width * scale + 100  # margin for dimensions
            svg_h = length * scale + 100

            svg_parts = [
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="-50 -50 {svg_w} {svg_h}">',
                '<style>text { font-family: Arial; font-size: 10px; } .dim { font-size: 8px; fill: #666; } .wall { fill: none; stroke: #333; stroke-width: 3; } .room { fill: #f5f5f5; stroke: #999; stroke-width: 1; }</style>',
            ]

            # Outer walls
            svg_parts.append(
                f'<rect x="0" y="0" width="{width * scale}" height="{length * scale}" class="wall"/>'
            )

            # Rooms
            for room in rooms:
                rx = room.get("x", 0)
                rz = room.get("z", 0)
                rw = room.get("w", 4)
                rd = room.get("d", 4)

                # Convert to SVG coordinates (center → top-left)
                svg_x = (width / 2 + rx - rw / 2) * scale
                svg_y = (length / 2 - rz - rd / 2) * scale

                svg_parts.append(
                    f'<rect x="{svg_x:.1f}" y="{svg_y:.1f}" width="{rw * scale:.1f}" height="{rd * scale:.1f}" class="room"/>'
                )

                # Room name
                if show_room_names:
                    name = room.get("n", "")
                    cx = svg_x + rw * scale / 2
                    cy = svg_y + rd * scale / 2
                    svg_parts.append(
                        f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" dominant-baseline="middle">{name}</text>'
                    )

            # Dimensions
            if show_dimensions:
                # Width dimension (top)
                svg_parts.append(
                    f'<text x="{width * scale / 2}" y="-20" text-anchor="middle" class="dim">{width}м</text>'
                )
                # Length dimension (left)
                svg_parts.append(
                    f'<text x="-20" y="{length * scale / 2}" text-anchor="middle" class="dim" transform="rotate(-90, -20, {length * scale / 2})">{length}м</text>'
                )

            svg_parts.append("</svg>")

            svg_content = "\n".join(svg_parts)

            if filepath is None:
                filepath = os.path.join(self.output_dir, f"floorplan_{uuid.uuid4().hex[:8]}.svg")

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(svg_content)

            logger.info("Exported floor plan SVG: %s", filepath)
            return filepath

        except Exception as e:
            logger.error("SVG export failed: %s", e)
            return None

    def occt_to_glb(self, occt_shape, filepath: Optional[str] = None) -> Optional[str]:
        """
        Convert OCCT shape to GLB via trimesh tessellation.

        This bridges cad_builder (OCCT) → Three.js viewer (GLB).
        """
        if not TRIMESH_AVAILABLE:
            return None

        try:
            # Tessellate OCCT shape
            from OCP.BRepMesh import BRepMesh_IncrementalMesh
            from OCP.StlAPI import StlAPI_Writer

            # First export to STL (temp), then load with trimesh
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
                tmp_path = tmp.name

            mesh = BRepMesh_IncrementalMesh(occt_shape, 0.01)
            mesh.Perform()

            writer = StlAPI_Writer()
            writer.Write(tmp_path)

            # Load STL into trimesh
            mesh_trimesh = trimesh.load(tmp_path)
            os.unlink(tmp_path)

            if filepath is None:
                filepath = os.path.join(self.output_dir, f"cad_{uuid.uuid4().hex[:8]}.glb")

            mesh_trimesh.export(filepath, file_type="glb")
            logger.info("OCCT → GLB: %s", filepath)
            return filepath

        except Exception as e:
            logger.error("OCCT → GLB conversion failed: %s", e)
            return None
