"""
shared/floorplan.py — Генерация SVG floor plan из параметров здания.

Использует Shapely для 2D-геометрии стен, окон, дверей.
Генерирует чистый SVG с аннотациями площадей.

Зависимости: shapely
"""

import math
from typing import Optional

from shared.validation import safe_val, DEFAULT_FURNITURE


def generate_floorplan_svg(params: dict, floor: int = 1) -> str:
    """
    Генерирует SVG-план этажа.

    Args:
        params: параметры здания
        floor: номер этажа (1-based)

    Returns:
        SVG-строка
    """
    W = safe_val(params.get("width"), 10, range(1, 201))
    L = safe_val(params.get("length"), 12, range(1, 201))
    fH = safe_val(params.get("floor_height"), 3.0)
    thick = safe_val(params.get("wall_thickness"), 0.3)

    # Масштаб: 1м = 40px
    scale = 40
    margin = 60
    svg_w = W * scale + margin * 2
    svg_l = L * scale + margin * 2

    # Смещение для центрирования
    ox = margin + W * scale / 2
    oy = margin + L * scale / 2

    def to_svg(x, y):
        """Конвертирует мировые координаты в SVG."""
        return (ox + x * scale, oy + y * scale)

    # Определяем помещения для этажа
    rooms = _get_rooms_for_floor(params, floor)

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_l}" '
        f'width="{svg_w}" height="{svg_l}" font-family="Inter, Arial, sans-serif">',
        f'<rect width="{svg_w}" height="{svg_l}" fill="#f8f8f8"/>',
    ]

    # === Фон этажа ===
    fx, fy = to_svg(-W / 2, -L / 2)
    svg_parts.append(
        f'<rect x="{fx}" y="{fy}" width="{W * scale}" height="{L * scale}" '
        f'fill="white" stroke="#333" stroke-width="3"/>'
    )

    # === Стены (толщина) ===
    wall_color = "#444"
    wall_w = thick * scale

    # Внешние стены
    for side, (sx, sy), (sw, sh) in [
        ("top", (-W / 2, -L / 2), (W, thick)),
        ("bottom", (-W / 2, L / 2 - thick), (W, thick)),
        ("left", (-W / 2, -L / 2), (thick, L)),
        ("right", (W / 2 - thick, -L / 2), (thick, L)),
    ]:
        wx, wy = to_svg(sx, sy)
        svg_parts.append(
            f'<rect x="{wx}" y="{wy}" width="{sw * scale}" height="{sh * scale}" '
            f'fill="{wall_color}"/>'
        )

    # === Помещения ===
    colors = [
        "#e8f4f8", "#f8e8e8", "#e8f8e8", "#f8f8e8",
        "#f0e8f8", "#e8f0f8", "#f8f0e8", "#e0f0e0",
    ]

    for i, room in enumerate(rooms):
        rx = room.get("x", 0)
        ry = room.get("y", 0)
        rw = room.get("w", 4)
        rd = room.get("d", 4)
        name = room.get("name", f"Room {i + 1}")

        # Позиция (rooms хранятся как center-based)
        sx, sy = to_svg(rx - rw / 2, ry - rd / 2)

        color = colors[i % len(colors)]
        svg_parts.append(
            f'<rect x="{sx}" y="{sy}" width="{rw * scale}" height="{rd * scale}" '
            f'fill="{color}" stroke="#999" stroke-width="1" opacity="0.7"/>'
        )

        # Название помещения
        tx, ty = to_svg(rx, ry)
        area = rw * rd
        svg_parts.append(
            f'<text x="{tx}" y="{ty - 6}" text-anchor="middle" '
            f'font-size="11" font-weight="600" fill="#333">{name}</text>'
        )
        svg_parts.append(
            f'<text x="{tx}" y="{ty + 10}" text-anchor="middle" '
            f'font-size="9" fill="#666">{area:.1f} м²</text>'
        )

        # Мебель (схематично)
        _add_furniture_svg(svg_parts, room, to_svg, scale)

    # === Окна ===
    n_win = max(2, W // 3)
    for i in range(n_win):
        x = -W / 2 + (i + 1) * W / (n_win + 1)
        # Передняя стена
        wx1, wy1 = to_svg(x - 0.6, -L / 2)
        svg_parts.append(
            f'<rect x="{wx1}" y="{wy1}" width="{1.2 * scale}" height="{thick * scale}" '
            f'fill="#87CEEB" stroke="#4682B4" stroke-width="1"/>'
        )
        # Задняя стена
        wx2, wy2 = to_svg(x - 0.6, L / 2 - thick)
        svg_parts.append(
            f'<rect x="{wx2}" y="{wy2}" width="{1.2 * scale}" height="{thick * scale}" '
            f'fill="#87CEEB" stroke="#4682B4" stroke-width="1"/>'
        )

    # === Дверь ===
    dx, dy = to_svg(-0.45, -L / 2)
    svg_parts.append(
        f'<rect x="{dx}" y="{dy}" width="{0.9 * scale}" height="{thick * scale}" '
        f'fill="#8B4513" stroke="#5C3317" stroke-width="1"/>'
    )
    # Дуга открывания двери
    door_cx, door_cy = to_svg(0, -L / 2)
    r = 0.9 * scale
    svg_parts.append(
        f'<path d="M {door_cx} {door_cy} '
        f'A {r} {r} 0 0 1 {door_cx + r} {door_cy}" '
        f'fill="none" stroke="#8B4513" stroke-width="0.5" stroke-dasharray="3,2"/>'
    )

    # === Размерные линии ===
    _add_dimensions(svg_parts, W, L, to_svg, scale)

    # === Компас ===
    cx, cy = to_svg(W / 2 + 1.5, -L / 2 - 1.5)
    svg_parts.append(
        f'<g transform="translate({cx},{cy})">'
        f'<circle r="12" fill="white" stroke="#999" stroke-width="0.5"/>'
        f'<text x="0" y="-3" text-anchor="middle" font-size="8" font-weight="700" fill="#c00">N</text>'
        f'<line x1="0" y1="-10" x2="0" y2="10" stroke="#999" stroke-width="0.5"/>'
        f'<line x1="-10" y1="0" x2="10" y2="0" stroke="#999" stroke-width="0.5"/>'
        f'</g>'
    )

    # === Масштабная лейка ===
    lx, ly = to_svg(-W / 2, L / 2 + 2)
    svg_parts.append(
        f'<line x1="{lx}" y1="{ly}" x2="{lx + 2 * scale}" y2="{ly}" '
        f'stroke="#333" stroke-width="1.5"/>'
    )
    svg_parts.append(
        f'<text x="{lx + scale}" y="{ly - 5}" text-anchor="middle" '
        f'font-size="9" fill="#333">2 м</text>'
    )

    # === Легенда ===
    lx2, ly2 = to_svg(-W / 2 - 1, L / 2 + 3.5)
    total_area = W * L
    svg_parts.append(
        f'<text x="{lx2}" y="{ly2}" font-size="10" fill="#333">'
        f'Этаж {floor} | {W}×{L} м | {total_area} м²</text>'
    )

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def _get_rooms_for_floor(params: dict, floor: int) -> list:
    """Возвращает помещения для указанного этажа."""
    W = params.get("width", 10)
    L = params.get("length", 12)
    rooms = params.get("rooms", [])

    if rooms:
        return [r for r in rooms if r.get("floor", 1) == floor]

    # Дефолтные помещения
    if floor == 1:
        return [
            {"name": "Гостиная", "x": -W / 4, "y": 0.5, "w": W / 2 - 0.5, "d": L / 2 - 0.5},
            {"name": "Кухня", "x": W / 4, "y": 0.5, "w": W / 2 - 0.5, "d": L / 2 - 0.5},
            {"name": "Прихожая", "x": 0, "y": -L / 4, "w": W / 3, "d": L / 4 - 0.5},
            {"name": "Санузел", "x": -W / 3, "y": -L / 4, "w": W / 4, "d": L / 4 - 0.5},
        ]
    elif floor == 2:
        return [
            {"name": "Спальня 1", "x": -W / 4, "y": 0.5, "w": W / 2 - 0.5, "d": L / 2 - 0.5},
            {"name": "Спальня 2", "x": W / 4, "y": 0.5, "w": W / 2 - 0.5, "d": L / 2 - 0.5},
            {"name": "Ванная", "x": 0, "y": -L / 4, "w": W / 3, "d": L / 4 - 0.5},
        ]
    return []


def _add_furniture_svg(svg_parts: list, room: dict, to_svg, scale: float):
    """Добавляет схематичную мебель в SVG."""
    name = room.get("name", "").lower()
    rx = room.get("x", 0)
    ry = room.get("y", 0)
    rw = room.get("w", 4)
    rd = room.get("d", 4)

    furn = []
    if "гостиная" in name or "living" in name:
        # Диван
        fx, fy = to_svg(rx - 0.5, ry + rd / 4)
        furn.append(f'<rect x="{fx}" y="{fy}" width="{1.8 * scale * 0.3}" '
                     f'height="{0.8 * scale * 0.3}" fill="#8B7355" rx="2" opacity="0.5"/>')
        # Столик
        tx, ty = to_svg(rx, ry)
        furn.append(f'<rect x="{tx - 6}" y="{ty - 4}" width="12" height="8" '
                     f'fill="#A0522D" rx="1" opacity="0.5"/>')
    elif "кухня" in name or "kitchen" in name:
        # Стол
        tx, ty = to_svg(rx, ry)
        furn.append(f'<rect x="{tx - 8}" y="{ty - 6}" width="16" height="12" '
                     f'fill="#DEB887" rx="1" opacity="0.5"/>')
    elif "спальн" in name or "bedroom" in name:
        # Кровать
        bx, by = to_svg(rx - 0.9, ry - 1)
        furn.append(f'<rect x="{bx}" y="{by}" width="{1.8 * scale * 0.3}" '
                     f'height="{2 * scale * 0.3}" fill="#E8E0D0" rx="2" opacity="0.5"/>')
    elif "ванн" in name or "bath" in name:
        # Ванна
        bx, by = to_svg(rx, ry)
        furn.append(f'<rect x="{bx - 10}" y="{by - 18}" width="20" height="36" '
                     f'fill="#E0E0E0" rx="8" opacity="0.5"/>')

    svg_parts.extend(furn)


def _add_dimensions(svg_parts: list, W: float, L: float, to_svg, scale: float):
    """Добавляет размерные линии."""
    color = "#666"
    lw = 0.8

    # Ширина (сверху)
    x1, y1 = to_svg(-W / 2, -L / 2 - 2)
    x2, y2 = to_svg(W / 2, -L / 2 - 2)
    svg_parts.append(
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{color}" stroke-width="{lw}"/>'
    )
    # Выноски
    svg_parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x1}" y2="{y1 + 10}" '
                      f'stroke="{color}" stroke-width="0.5"/>')
    svg_parts.append(f'<line x1="{x2}" y1="{y2}" x2="{x2}" y2="{y2 + 10}" '
                      f'stroke="{color}" stroke-width="0.5"/>')
    mx, my = to_svg(0, -L / 2 - 3)
    svg_parts.append(
        f'<text x="{mx}" y="{my}" text-anchor="middle" font-size="10" fill="{color}">'
        f'{W} м</text>'
    )

    # Длина (справа)
    x1, y1 = to_svg(W / 2 + 2, -L / 2)
    x2, y2 = to_svg(W / 2 + 2, L / 2)
    svg_parts.append(
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{color}" stroke-width="{lw}"/>'
    )
    svg_parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x1 - 10}" y2="{y1}" '
                      f'stroke="{color}" stroke-width="0.5"/>')
    svg_parts.append(f'<line x1="{x2}" y1="{y2}" x2="{x2 - 10}" y2="{y2}" '
                      f'stroke="{color}" stroke-width="0.5"/>')
    mx, my = to_svg(W / 2 + 3.5, 0)
    svg_parts.append(
        f'<text x="{mx}" y="{my}" text-anchor="middle" font-size="10" fill="{color}" '
        f'transform="rotate(90,{mx},{my})">{L} м</text>'
    )
