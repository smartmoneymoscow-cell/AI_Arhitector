"""
shared/agents/drawings_svg.py — Генератор качественных чертежей SVG.

Генерирует:
- План этажей (floor plan)
- Разрез здания (section)
- Фасад (elevation)
- Схема инженерных систем (MEP diagram)

Каждый чертёж — отдельный SVG, согласованный с 3D моделью.
"""

import math


def generate_floor_plan_svg(params: dict, rooms: list = None) -> str:
    """
    Генерирует SVG плана этажа.

    Args:
        params: параметры здания (width, length, floors, height)
        rooms: список помещений [{name, x, y, w, d, floor, tag}]

    Returns:
        SVG строка
    """
    width = params.get("width_m", params.get("width", 10))
    length = params.get("length_m", params.get("length", 12))
    floor = params.get("current_floor", 1)

    # Scale: 1m = 60px
    scale = 60
    margin = 40
    svg_w = int(width * scale + margin * 2)
    svg_h = int(length * scale + margin * 2)

    # Offset to center
    ox = margin + int(width * scale / 2)
    oy = margin + int(length * scale / 2)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}">',
        f'<style>',
        f'  .wall {{ fill: none; stroke: #1a2230; stroke-width: 3; }}',
        f'  .wall-thin {{ fill: none; stroke: #1a2230; stroke-width: 1.5; }}',
        f'  .dim {{ font-family: Arial; font-size: 10px; fill: #1d4ed8; }}',
        f'  .dim-line {{ stroke: #1d4ed8; stroke-width: 0.5; }}',
        f'  .room-label {{ font-family: Arial; font-size: 11px; fill: #0f172a; text-anchor: middle; }}',
        f'  .room-area {{ font-family: Arial; font-size: 9px; fill: #64748b; text-anchor: middle; }}',
        f'  .door {{ fill: none; stroke: #3d2010; stroke-width: 1.5; }}',
        f'  .window {{ fill: #bfe3f5; stroke: #0e7490; stroke-width: 1; }}',
        f'  .furniture {{ fill: #e2e8f0; stroke: #94a3b8; stroke-width: 0.5; }}',
        f'  .grid {{ stroke: #eef2f7; stroke-width: 0.3; }}',
        f'  .title {{ font-family: Arial; font-size: 14px; font-weight: bold; fill: #0f172a; }}',
        f'  .subtitle {{ font-family: Arial; font-size: 10px; fill: #64748b; }}',
        f'</style>',
        f'',
        f'<!-- Background -->',
        f'<rect width="{svg_w}" height="{svg_h}" fill="#ffffff"/>',
        f'',
        f'<!-- Grid -->',
    ]

    # Grid
    for gx in range(0, int(width) + 1):
        x = ox - int(width * scale / 2) + gx * scale
        lines.append(f'<line x1="{x}" y1="{margin}" x2="{x}" y2="{svg_h - margin}" class="grid"/>')
    for gy in range(0, int(length) + 1):
        y = oy - int(length * scale / 2) + gy * scale
        lines.append(f'<line x1="{margin}" y1="{y}" x2="{svg_w - margin}" y2="{y}" class="grid"/>')

    lines.append('')

    # Outer walls
    x1 = ox - int(width * scale / 2)
    y1 = oy - int(length * scale / 2)
    x2 = ox + int(width * scale / 2)
    y2 = oy + int(length * scale / 2)
    lines.append(f'<!-- Outer walls -->')
    lines.append(f'<rect x="{x1}" y="{y1}" width="{int(width * scale)}" height="{int(length * scale)}" class="wall"/>')

    lines.append('')

    # Rooms
    if rooms:
        lines.append(f'<!-- Rooms -->')
        for room in rooms:
            if room.get("floor", 1) != floor:
                continue
            rx = ox + int(room.get("x", 0) * scale)
            ry = oy + int(room.get("y", 0) * scale)
            rw = int(room.get("w", 3) * scale)
            rd = int(room.get("d", 3) * scale)
            name = room.get("n", room.get("name", ""))
            area = room.get("a", room.get("w", 3) * room.get("d", 3))

            lines.append(f'<rect x="{rx - rw // 2}" y="{ry - rd // 2}" width="{rw}" height="{rd}" class="wall-thin"/>')
            lines.append(f'<text x="{rx}" y="{ry - 4}" class="room-label">{name}</text>')
            lines.append(f'<text x="{rx}" y="{ry + 8}" class="room-area">{area} м²</text>')

            # Door opening (simple gap in wall)
            lines.append(f'<line x1="{rx - rw // 2}" y1="{ry + rd // 2 - 10}" x2="{rx - rw // 2 + 15}" y2="{ry + rd // 2 - 10}" stroke="#ffffff" stroke-width="3"/>')

    lines.append('')

    # Dimensions
    lines.append(f'<!-- Dimensions -->')
    # Width (bottom)
    dim_y = y2 + 20
    lines.append(f'<line x1="{x1}" y1="{dim_y}" x2="{x2}" y2="{dim_y}" class="dim-line"/>')
    lines.append(f'<line x1="{x1}" y1="{dim_y - 4}" x2="{x1}" y2="{dim_y + 4}" class="dim-line"/>')
    lines.append(f'<line x1="{x2}" y1="{dim_y - 4}" x2="{x2}" y2="{dim_y + 4}" class="dim-line"/>')
    lines.append(f'<text x="{(x1 + x2) // 2}" y="{dim_y - 6}" class="dim" text-anchor="middle">{width} м</text>')

    # Length (right)
    dim_x = x2 + 20
    lines.append(f'<line x1="{dim_x}" y1="{y1}" x2="{dim_x}" y2="{y2}" class="dim-line"/>')
    lines.append(f'<line x1="{dim_x - 4}" y1="{y1}" x2="{dim_x + 4}" y2="{y1}" class="dim-line"/>')
    lines.append(f'<line x1="{dim_x - 4}" y1="{y2}" x2="{dim_x + 4}" y2="{y2}" class="dim-line"/>')
    lines.append(f'<text x="{dim_x + 6}" y="{(y1 + y2) // 2}" class="dim" transform="rotate(90,{dim_x + 6},{(y1 + y2) // 2})">{length} м</text>')

    # Title block
    lines.append(f'<!-- Title -->')
    lines.append(f'<text x="{margin}" y="{svg_h - 10}" class="title">План этажа {floor}</text>')
    lines.append(f'<text x="{margin}" y="{svg_h - 25}" class="subtitle">{width}×{length} м | Масштаб 1:{int(1000 / scale) if scale else 60}</text>')

    lines.append('</svg>')
    return "\n".join(lines)


def generate_section_svg(params: dict) -> str:
    """
    Генерирует SVG разреза здания.

    Returns:
        SVG строка
    """
    width = params.get("width_m", params.get("width", 10))
    floors = params.get("floors", 2)
    fH = params.get("height_m", params.get("height", 3.0))
    total_h = fH * floors
    roof_type = params.get("roof_type", "gabled")
    material = params.get("material", "plaster")

    scale = 50
    margin = 50
    svg_w = int(width * scale + margin * 2)
    svg_h = int(total_h * scale + margin * 2 + 60)

    ox = margin + int(width * scale / 2)
    oy = margin + int(total_h * scale)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}">',
        f'<style>',
        f'  .wall-section {{ fill: #cbd2dc; stroke: #1a2230; stroke-width: 2; }}',
        f'  .floor-section {{ fill: #94a3b8; stroke: #1a2230; stroke-width: 1.5; }}',
        f'  .roof-section {{ fill: #9a6a3c; stroke: #5c3a18; stroke-width: 1.5; }}',
        f'  .foundation {{ fill: #aab2bd; stroke: #475569; stroke-width: 2; }}',
        f'  .dim {{ font-family: Arial; font-size: 10px; fill: #1d4ed8; }}',
        f'  .dim-line {{ stroke: #1d4ed8; stroke-width: 0.5; }}',
        f'  .label {{ font-family: Arial; font-size: 10px; fill: #64748b; }}',
        f'  .hatch {{ stroke: #94a3b8; stroke-width: 0.3; }}',
        f'  .title {{ font-family: Arial; font-size: 14px; font-weight: bold; fill: #0f172a; }}',
        f'</style>',
        f'<rect width="{svg_w}" height="{svg_h}" fill="#ffffff"/>',
    ]

    # Foundation
    fnd_h = 0.8 * scale
    x1 = ox - int(width * scale / 2)
    x2 = ox + int(width * scale / 2)
    fnd_y = oy

    lines.append(f'<!-- Foundation -->')
    lines.append(f'<rect x="{x1 - 10}" y="{fnd_y}" width="{int(width * scale) + 20}" height="{int(fnd_h)}" class="foundation"/>')
    # Hatch pattern
    for hx in range(x1 - 5, x2 + 15, 8):
        lines.append(f'<line x1="{hx}" y1="{fnd_y}" x2="{hx + 8}" y2="{fnd_y + int(fnd_h)}" class="hatch"/>')

    # Walls and floors
    wall_thick = 0.3 * scale
    for fl in range(floors):
        y_bottom = oy - int((fl + 1) * fH * scale)
        y_top = oy - int(fl * fH * scale)

        # Left wall
        lines.append(f'<rect x="{x1}" y="{y_bottom}" width="{int(wall_thick)}" height="{int(fH * scale)}" class="wall-section"/>')
        # Right wall
        lines.append(f'<rect x="{x2 - int(wall_thick)}" y="{y_bottom}" width="{int(wall_thick)}" height="{int(fH * scale)}" class="wall-section"/>')

        # Floor slab (except ground floor)
        if fl > 0:
            slab_h = 0.2 * scale
            lines.append(f'<rect x="{x1}" y="{y_top - int(slab_h)}" width="{int(width * scale)}" height="{int(slab_h)}" class="floor-section"/>')

        # Room label
        lines.append(f'<text x="{ox}" y="{(y_bottom + y_top) // 2}" class="label" text-anchor="middle">Этаж {fl + 1}</text>')

        # Window in section
        win_y = y_bottom + int(fH * scale * 0.3)
        win_h = int(fH * scale * 0.4)
        lines.append(f'<rect x="{x1}" y="{win_y}" width="{int(wall_thick)}" height="{win_h}" fill="#bfe3f5" stroke="#0e7490"/>')
        lines.append(f'<rect x="{x2 - int(wall_thick)}" y="{win_y}" width="{int(wall_thick)}" height="{win_h}" fill="#bfe3f5" stroke="#0e7490"/>')

    # Roof
    roof_top = oy - int(total_h * scale)
    lines.append(f'<!-- Roof -->')
    if "двускатн" in str(roof_type).lower() or "gable" in str(roof_type).lower():
        slope = 35
        ridge_h = (width / 2) * math.tan(math.radians(slope)) * scale
        lines.append(f'<polygon points="{x1},{roof_top} {ox},{roof_top - int(ridge_h)} {x2},{roof_top}" class="roof-section"/>')
    elif "плоск" in str(roof_type).lower() or "flat" in str(roof_type).lower():
        lines.append(f'<rect x="{x1 - 10}" y="{roof_top - int(0.3 * scale)}" width="{int(width * scale) + 20}" height="{int(0.3 * scale)}" class="roof-section"/>')

    # Dimensions (left side)
    dim_x = x1 - 30
    for fl in range(floors + 1):
        y = oy - int(fl * fH * scale)
        lines.append(f'<line x1="{dim_x - 5}" y1="{y}" x2="{x1}" y2="{y}" class="dim-line" stroke-dasharray="3,3"/>')
    lines.append(f'<line x1="{dim_x}" y1="{oy}" x2="{dim_x}" y2="{oy - int(total_h * scale)}" class="dim-line"/>')
    lines.append(f'<text x="{dim_x - 5}" y="{oy - int(total_h * scale / 2)}" class="dim" text-anchor="end">{total_h} м</text>')

    # Floor heights
    for fl in range(floors):
        y_b = oy - int((fl + 1) * fH * scale)
        y_t = oy - int(fl * fH * scale)
        lines.append(f'<line x1="{x2 + 10}" y1="{y_b}" x2="{x2 + 10}" y2="{y_t}" class="dim-line"/>')
        lines.append(f'<text x="{x2 + 15}" y="{(y_b + y_t) // 2}" class="dim">{fH} м</text>')

    # Title
    lines.append(f'<text x="{margin}" y="{svg_h - 10}" class="title">Разрез здания</text>')
    lines.append('</svg>')
    return "\n".join(lines)


def generate_elevation_svg(params: dict, side: str = "front") -> str:
    """
    Генерирует SVG фасада.

    Args:
        params: параметры здания
        side: "front", "back", "left", "right"

    Returns:
        SVG строка
    """
    width = params.get("width_m", params.get("width", 10))
    length = params.get("length_m", params.get("length", 12))
    floors = params.get("floors", 2)
    fH = params.get("height_m", params.get("height", 3.0))
    total_h = fH * floors
    material = params.get("material", "plaster")
    roof_type = params.get("roof_type", "gabled")

    # Front/back shows width, left/right shows length
    facade_w = width if side in ("front", "back") else length

    scale = 50
    margin = 50
    svg_w = int(facade_w * scale + margin * 2)
    svg_h = int(total_h * scale + margin * 2 + 80)

    ox = margin + int(facade_w * scale / 2)
    oy = margin + int(total_h * scale) + 20

    # Material color
    mat_colors = {
        "brick": "#c87040",
        "wood": "#b8864e",
        "glass": "#7ec8e3",
        "plaster": "#f0ece4",
        "stone": "#8a8278",
        "concrete": "#a0a0a0",
    }
    wall_color = mat_colors.get(material, "#f0ece4")

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}">',
        f'<style>',
        f'  .wall-facade {{ fill: {wall_color}; stroke: #1a2230; stroke-width: 2; }}',
        f'  .window-facade {{ fill: #bfe3f5; stroke: #0e7490; stroke-width: 1; }}',
        f'  .door-facade {{ fill: #3d2010; stroke: #1a2230; stroke-width: 1.5; }}',
        f'  .roof-facade {{ fill: #9a6a3c; stroke: #5c3a18; stroke-width: 1.5; }}',
        f'  .dim {{ font-family: Arial; font-size: 10px; fill: #1d4ed8; }}',
        f'  .dim-line {{ stroke: #1d4ed8; stroke-width: 0.5; }}',
        f'  .label {{ font-family: Arial; font-size: 10px; fill: #64748b; }}',
        f'  .title {{ font-family: Arial; font-size: 14px; font-weight: bold; fill: #0f172a; }}',
        f'</style>',
        f'<rect width="{svg_w}" height="{svg_h}" fill="#ffffff"/>',
    ]

    x1 = ox - int(facade_w * scale / 2)
    x2 = ox + int(facade_w * scale / 2)
    y1 = oy - int(total_h * scale)
    y2 = oy

    # Main wall
    lines.append(f'<rect x="{x1}" y="{y1}" width="{int(facade_w * scale)}" height="{int(total_h * scale)}" class="wall-facade"/>')

    # Floor lines
    for fl in range(1, floors):
        fy = oy - int(fl * fH * scale)
        lines.append(f'<line x1="{x1}" y1="{fy}" x2="{x2}" y2="{fy}" stroke="#1a2230" stroke-width="0.5"/>')

    # Windows
    win_w = 1.2 * scale
    win_h = 1.4 * scale
    for fl in range(floors):
        wy = oy - int((fl + 0.3) * fH * scale) - int(win_h)
        for wx_offset in [-facade_w / 3, 0, facade_w / 3]:
            wx = ox + int(wx_offset * scale) - int(win_w / 2)
            lines.append(f'<rect x="{wx}" y="{wy}" width="{int(win_w)}" height="{int(win_h)}" class="window-facade"/>')
            # Window cross
            lines.append(f'<line x1="{wx + int(win_w / 2)}" y1="{wy}" x2="{wx + int(win_w / 2)}" y2="{wy + int(win_h)}" stroke="#0e7490" stroke-width="0.5"/>')
            lines.append(f'<line x1="{wx}" y1="{wy + int(win_h / 2)}" x2="{wx + int(win_w)}" y2="{wy + int(win_h / 2)}" stroke="#0e7490" stroke-width="0.5"/>')

    # Door (front only)
    if side == "front":
        door_w = 1.0 * scale
        door_h = 2.1 * scale
        dx = ox - int(door_w / 2)
        dy = oy - int(door_h)
        lines.append(f'<rect x="{dx}" y="{dy}" width="{int(door_w)}" height="{int(door_h)}" class="door-facade"/>')
        # Door handle
        lines.append(f'<circle cx="{dx + int(door_w * 0.8)}" cy="{oy - int(door_h * 0.45)}" r="3" fill="#b8860c"/>')

    # Roof
    if "двускатн" in str(roof_type).lower() or "gable" in str(roof_type).lower():
        slope = 35
        ridge_h = (facade_w / 2) * math.tan(math.radians(slope)) * scale
        lines.append(f'<polygon points="{x1 - 10},{y1} {ox},{y1 - int(ridge_h)} {x2 + 10},{y1}" class="roof-facade"/>')
        # Ridge line
        lines.append(f'<line x1="{x1 - 10}" y1="{y1}" x2="{x2 + 10}" y2="{y1}" stroke="#5c3a18" stroke-width="2"/>')
    elif "плоск" in str(roof_type).lower() or "flat" in str(roof_type).lower():
        lines.append(f'<rect x="{x1 - 10}" y="{y1 - int(0.2 * scale)}" width="{int(facade_w * scale) + 20}" height="{int(0.2 * scale)}" class="roof-facade"/>')

    # Dimensions
    dim_y = y2 + 25
    lines.append(f'<line x1="{x1}" y1="{dim_y}" x2="{x2}" y2="{dim_y}" class="dim-line"/>')
    lines.append(f'<text x="{ox}" y="{dim_y - 5}" class="dim" text-anchor="middle">{facade_w} м</text>')

    dim_x = x2 + 20
    lines.append(f'<line x1="{dim_x}" y1="{y1}" x2="{dim_x}" y2="{y2}" class="dim-line"/>')
    lines.append(f'<text x="{dim_x + 5}" y="{(y1 + y2) // 2}" class="dim">{total_h} м</text>')

    # Title
    side_names = {"front": "Главный фасад", "back": "Задний фасад", "left": "Левый фасад", "right": "Правый фасад"}
    lines.append(f'<text x="{margin}" y="{svg_h - 10}" class="title">{side_names.get(side, "Фасад")}</text>')
    lines.append(f'<text x="{margin}" y="{svg_h - 25}" class="label">{material} | {floors} эт.</text>')
    lines.append('</svg>')
    return "\n".join(lines)


def generate_mep_diagram_svg(params: dict, mep_calc: dict) -> str:
    """
    Генерирует SVG схемы инженерных систем.

    Returns:
        SVG строка
    """
    width = params.get("width_m", params.get("width", 10))
    length = params.get("length_m", params.get("length", 12))

    scale = 50
    margin = 50
    svg_w = int(width * scale + margin * 2)
    svg_h = int(length * scale + margin * 2 + 60)

    ox = margin + int(width * scale / 2)
    oy = margin + int(length * scale / 2)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}">',
        f'<style>',
        f'  .cold-water {{ fill: none; stroke: #1e40af; stroke-width: 2; }}',
        f'  .hot-water {{ fill: none; stroke: #dc2626; stroke-width: 2; }}',
        f'  .sewer {{ fill: none; stroke: #78350f; stroke-width: 2.5; }}',
        f'  .electrical {{ fill: none; stroke: #15803d; stroke-width: 1.5; stroke-dasharray: 5,3; }}',
        f'  .vent {{ fill: none; stroke: #6b7280; stroke-width: 2; }}',
        f'  .label {{ font-family: Arial; font-size: 9px; }}',
        f'  .title {{ font-family: Arial; font-size: 14px; font-weight: bold; fill: #0f172a; }}',
        f'</style>',
        f'<rect width="{svg_w}" height="{svg_h}" fill="#ffffff"/>',
    ]

    x1 = ox - int(width * scale / 2)
    y1 = oy - int(length * scale / 2)
    x2 = ox + int(width * scale / 2)
    y2 = oy + int(length * scale / 2)

    # Building outline
    lines.append(f'<rect x="{x1}" y="{y1}" width="{int(width * scale)}" height="{int(length * scale)}" fill="none" stroke="#1a2230" stroke-width="1" stroke-dasharray="4,2"/>')

    # Cold water (blue, left side)
    cw_x = x1 + int(0.3 * scale)
    lines.append(f'<line x1="{cw_x}" y1="{y1}" x2="{cw_x}" y2="{y2}" class="cold-water"/>')
    lines.append(f'<text x="{cw_x + 5}" y="{y1 + 15}" class="label" fill="#1e40af">ХВС</text>')

    # Hot water (red, left side)
    hw_x = x1 + int(0.5 * scale)
    lines.append(f'<line x1="{hw_x}" y1="{y1}" x2="{hw_x}" y2="{y2}" class="hot-water"/>')
    lines.append(f'<text x="{hw_x + 5}" y="{y1 + 15}" class="label" fill="#dc2626">ГВС</text>')

    # Sewer (brown, left side with slope)
    sw_x = x1 + int(0.3 * scale)
    lines.append(f'<line x1="{sw_x + int(0.3 * scale)}" y1="{y1}" x2="{sw_x}" y2="{y2}" class="sewer"/>')
    lines.append(f'<text x="{sw_x + int(0.3 * scale) + 5}" y="{y1 + 25}" class="label" fill="#78350f">Канализация</text>')

    # Electrical (green, from panel)
    panel_x = x1 + int(0.15 * scale)
    panel_y = oy
    lines.append(f'<rect x="{panel_x - 5}" y="{panel_y - 10}" width="10" height="20" fill="#15803d" stroke="#0f172a"/>')
    lines.append(f'<text x="{panel_x + 8}" y="{panel_y + 5}" class="label" fill="#15803d">ЩУЭ</text>')
    lines.append(f'<line x1="{panel_x}" y1="{panel_y}" x2="{x2 - int(0.3 * scale)}" y2="{panel_y}" class="electrical"/>')

    # Ventilation (gray, horizontal at top)
    vent_y = y1 + int(0.2 * scale)
    lines.append(f'<line x1="{x1 + int(0.5 * scale)}" y1="{vent_y}" x2="{x2 - int(0.5 * scale)}" y2="{vent_y}" class="vent"/>')
    lines.append(f'<text x="{ox}" y="{vent_y - 5}" class="label" fill="#6b7280" text-anchor="middle">Вентиляция</text>')

    # Legend
    ly = svg_h - 40
    lines.append(f'<text x="{margin}" y="{ly}" class="title">Схема инженерных систем</text>')
    lines.append(f'<line x1="{margin}" y1="{ly + 10}" x2="{margin + 20}" y2="{ly + 10}" class="cold-water"/><text x="{margin + 25}" y="{ly + 13}" class="label">ХВС</text>')
    lines.append(f'<line x1="{margin + 60}" y1="{ly + 10}" x2="{margin + 80}" y2="{ly + 10}" class="hot-water"/><text x="{margin + 85}" y="{ly + 13}" class="label">ГВС</text>')
    lines.append(f'<line x1="{margin + 120}" y1="{ly + 10}" x2="{margin + 140}" y2="{ly + 10}" class="sewer"/><text x="{margin + 145}" y="{ly + 13}" class="label">Канализация</text>')
    lines.append(f'<line x1="{margin + 200}" y1="{ly + 10}" x2="{margin + 220}" y2="{ly + 10}" class="electrical"/><text x="{margin + 225}" y="{ly + 13}" class="label">Электрика</text>')

    lines.append('</svg>')
    return "\n".join(lines)
