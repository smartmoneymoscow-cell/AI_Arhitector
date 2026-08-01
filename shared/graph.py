"""
shared/graph.py — Граф здания на NetworkX.

Создаёт и анализирует граф связей между помещениями:
- Смежность комнат (общие стены)
- Маршруты эвакуации
- Оптимизация планировки
- Визуализация графа

Зависимости: networkx

Использование:
    from shared.graph import BuildingGraph
    bg = BuildingGraph.from_params(params)
    bg.get_adjacency_list()
    bg.find_path("Kitchen", "Exit")
"""


class BuildingGraph:
    """Граф связей помещений здания."""

    def __init__(self):
        self.graph = None
        self.rooms = []
        self.edges = []

    @classmethod
    def from_params(cls, params: dict) -> "BuildingGraph":
        """Создаёт граф из параметров здания."""
        bg = cls()
        bg.rooms = cls._extract_rooms(params)
        bg.edges = cls._calculate_adjacency(bg.rooms, params)
        return bg

    @staticmethod
    def _extract_rooms(params: dict) -> list:
        """Извлекает помещения из параметров."""
        W = params.get("width", 10)
        L = params.get("length", 12)
        floors = params.get("floors", 2)

        rooms = []
        room_configs = {
            1: [
                {
                    "name": "Living Room",
                    "floor": 1,
                    "x": -W / 4,
                    "y": 0,
                    "w": W / 2 - 0.5,
                    "d": L / 2 - 0.5,
                    "type": "living",
                },
                {
                    "name": "Kitchen",
                    "floor": 1,
                    "x": W / 4,
                    "y": 0,
                    "w": W / 2 - 0.5,
                    "d": L / 2 - 0.5,
                    "type": "kitchen",
                },
                {
                    "name": "Hallway",
                    "floor": 1,
                    "x": 0,
                    "y": -L / 4,
                    "w": W / 3,
                    "d": L / 4 - 0.5,
                    "type": "circulation",
                },
                {"name": "Bathroom", "floor": 1, "x": -W / 3, "y": -L / 4, "w": W / 4, "d": L / 4 - 0.5, "type": "wet"},
                {"name": "Entrance", "floor": 1, "x": 0, "y": -L / 2 + 1, "w": 2, "d": 2, "type": "entrance"},
            ],
            2: [
                {
                    "name": "Master Bedroom",
                    "floor": 2,
                    "x": -W / 4,
                    "y": 0,
                    "w": W / 2 - 0.5,
                    "d": L / 2 - 0.5,
                    "type": "bedroom",
                },
                {
                    "name": "Bedroom 2",
                    "floor": 2,
                    "x": W / 4,
                    "y": 0,
                    "w": W / 2 - 0.5,
                    "d": L / 2 - 0.5,
                    "type": "bedroom",
                },
                {"name": "Bathroom 2", "floor": 2, "x": 0, "y": -L / 4, "w": W / 4, "d": L / 4 - 0.5, "type": "wet"},
                {"name": "Hallway 2", "floor": 2, "x": 0, "y": 0, "w": W / 3, "d": L / 4, "type": "circulation"},
            ],
        }

        for floor in range(1, floors + 1):
            if floor in room_configs:
                rooms.extend(room_configs[floor])
            else:
                # Этажи выше 2 — копия 2-го
                for room in room_configs.get(2, []):
                    r = room.copy()
                    r["floor"] = floor
                    r["name"] = r["name"].replace(" 2", f" {floor}")
                    rooms.append(r)

        return rooms

    @staticmethod
    def _calculate_adjacency(rooms: list, params: dict) -> list:
        """Вычисляет смежность помещений (общие стены)."""
        edges = []
        threshold = 1.5  # Макс. расстояние между центрами для "смежности"

        for i, r1 in enumerate(rooms):
            for j, r2 in enumerate(rooms):
                if j <= i:
                    continue
                if r1["floor"] != r2["floor"]:
                    continue

                # Расстояние между центрами
                dx = abs(r1["x"] - r2["x"])
                dy = abs(r1["y"] - r2["y"])

                # Смежность: рядом по одной оси
                combined_w = (r1["w"] + r2["w"]) / 2
                combined_d = (r1["d"] + r2["d"]) / 2

                if (dx < combined_w + threshold and dy < combined_d / 2) or (
                    dy < combined_d + threshold and dx < combined_w / 2
                ):
                    edges.append(
                        {
                            "from": r1["name"],
                            "to": r2["name"],
                            "floor": r1["floor"],
                            "type": "adjacent",
                        }
                    )

                # Связь через коридор
                if r1.get("type") == "circulation" or r2.get("type") == "circulation":
                    dist = ((r1["x"] - r2["x"]) ** 2 + (r1["y"] - r2["y"]) ** 2) ** 0.5
                    if dist < max(combined_w, combined_d) * 1.5:
                        if {
                            "from": r1["name"],
                            "to": r2["name"],
                            "floor": r1["floor"],
                            "type": "adjacent",
                        } not in edges:
                            edges.append(
                                {
                                    "from": r1["name"],
                                    "to": r2["name"],
                                    "floor": r1["floor"],
                                    "type": "via_corridor",
                                }
                            )

                # Связь через лестницу (между этажами)
                if r1["floor"] != r2["floor"]:
                    if r1.get("type") == "circulation" and r2.get("type") == "circulation":
                        edges.append(
                            {
                                "from": r1["name"],
                                "to": r2["name"],
                                "floor": 0,  # межэтажная
                                "type": "stairs",
                            }
                        )

        return edges

    def to_networkx(self):
        """Конвертирует в NetworkX граф."""
        try:
            import networkx as nx
        except ImportError:
            raise ImportError("networkx не установлен. Установите: pip install networkx")

        G = nx.Graph()

        for room in self.rooms:
            G.add_node(room["name"], **room)

        for edge in self.edges:
            G.add_edge(edge["from"], edge["to"], type=edge["type"], floor=edge["floor"])

        self.graph = G
        return G

    def get_adjacency_list(self) -> dict:
        """Возвращает список смежности."""
        adj = {}
        for edge in self.edges:
            adj.setdefault(edge["from"], []).append(edge["to"])
            adj.setdefault(edge["to"], []).append(edge["from"])
        return adj

    def find_path(self, start: str, end: str) -> list:
        """Находит кратчайший путь между помещениями."""
        if self.graph is None:
            self.to_networkx()

        try:
            import networkx as nx

            return nx.shortest_path(self.graph, start, end)
        except Exception:
            return []

    def get_room_stats(self) -> dict:
        """Возвращает статистику по помещениям."""
        stats = {
            "total_rooms": len(self.rooms),
            "total_edges": len(self.edges),
            "floors": max(r["floor"] for r in self.rooms) if self.rooms else 0,
            "by_type": {},
            "by_floor": {},
        }

        for room in self.rooms:
            rtype = room.get("type", "unknown")
            stats["by_type"][rtype] = stats["by_type"].get(rtype, 0) + 1
            floor = room["floor"]
            stats["by_floor"][floor] = stats["by_floor"].get(floor, 0) + 1

        return stats

    def to_svg_graph(self) -> str:
        """Генерирует SVG-визуализацию графа связей."""
        if not self.rooms:
            return '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><text x="10" y="50">No rooms</text></svg>'

        # Группируем по этажам
        floors = {}
        for room in self.rooms:
            f = room["floor"]
            floors.setdefault(f, []).append(room)

        svg_w = 600
        floor_h = 200
        svg_h = len(floors) * floor_h + 80

        parts = [
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" '
                f'width="{svg_w}" height="{svg_h}" font-family="Inter, Arial, sans-serif">'
            ),
            f'<rect width="{svg_w}" height="{svg_h}" fill="#fafafa"/>',
        ]

        node_positions = {}
        colors = {
            "living": "#4CAF50",
            "kitchen": "#FF9800",
            "bedroom": "#2196F3",
            "bathroom": "#9C27B0",
            "wet": "#9C27B0",
            "circulation": "#607D8B",
            "entrance": "#F44336",
        }

        for floor_num, rooms in sorted(floors.items()):
            y_offset = (floor_num - 1) * floor_h + 40
            parts.append(
                f'<text x="10" y="{y_offset - 10}" font-size="12" font-weight="700" fill="#333">Этаж {floor_num}</text>'
            )

            n = len(rooms)
            for i, room in enumerate(rooms):
                x = 80 + i * (svg_w - 100) / max(n - 1, 1)
                y = y_offset + 60
                node_positions[room["name"]] = (x, y)

                color = colors.get(room.get("type", ""), "#757575")
                parts.append(f'<circle cx="{x}" cy="{y}" r="25" fill="{color}" opacity="0.8"/>')
                parts.append(
                    f'<text x="{x}" y="{y + 4}" text-anchor="middle" font-size="8" '
                    f'fill="white" font-weight="600">{room["name"][:12]}</text>'
                )

        # Рёбра
        for edge in self.edges:
            if edge["from"] in node_positions and edge["to"] in node_positions:
                x1, y1 = node_positions[edge["from"]]
                x2, y2 = node_positions[edge["to"]]

                stroke_color = (
                    "#2196F3"
                    if edge["type"] == "adjacent"
                    else "#FF9800"
                    if edge["type"] == "via_corridor"
                    else "#F44336"
                )
                dash = 'stroke-dasharray="4,2"' if edge["type"] == "stairs" else ""

                parts.append(
                    f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                    f'stroke="{stroke_color}" stroke-width="1.5" opacity="0.4" {dash}/>'
                )

        parts.append("</svg>")
        return "\n".join(parts)
