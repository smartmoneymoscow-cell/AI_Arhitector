"""
shared/ifc_generator.py — Генерация IFC-файлов из параметров здания.

Использует IfcOpenShell для создания настоящих BIM-объектов:
- IfcWall, IfcWindow, IfcDoor, IfcSlab, IfcRoof
- IfcSpace (помещения)
- IfcPropertySet (параметры)
- IFC2x3 и IFC4

Зависимости: ifcopenshell
"""

import os
import math
import uuid
from typing import Optional

from shared.validation import safe_val


def generate_ifc_building(params: dict, output_path: str, schema: str = "IFC2X3") -> str:
    """
    Генерирует IFC-файл здания из параметров.

    Args:
        params: параметры здания (width, length, floors, и т.д.)
        output_path: путь для сохранения .ifc файла
        schema: "IFC2X3" или "IFC4"

    Returns:
        Путь к созданному IFC-файлу

    Raises:
        ImportError: если ifcopenshell не установлен
        ValueError: при ошибках генерации
    """
    try:
        import ifcopenshell
        import ifcopenshell.api
        import ifcopenshell.guid
    except ImportError:
        raise ImportError(
            "ifcopenshell не установлен. Установите: pip install ifcopenshell"
        )

    W = safe_val(params.get("width"), 10, range(1, 201))
    L = safe_val(params.get("length"), 12, range(1, 201))
    floors = safe_val(params.get("floors"), 2, range(1, 21))
    fH = safe_val(params.get("floor_height"), 3.0)
    thick = safe_val(params.get("wall_thickness"), 0.3)
    mat = params.get("material", "plaster")
    roof_type = params.get("roof_type", "gabled")

    # Создание IFC-модели
    model = ifcopenshell.file(schema=schema)

    # === Owner History ===
    person = model.createIfcPerson(
        FamilyName="AI",
        GivenName="Architect",
    )
    org = model.createIfcOrganization(Name="AI_Arhitector")
    person_org = model.createIfcPersonAndOrganization(person, org)

    app = model.createIfcApplication(
        ApplicationDeveloper=org,
        Version="11.0",
        ApplicationFullName="AI_Arhitector BIM Generator",
        ApplicationIdentifier="archai-bim",
    )
    owner_history = model.createIfcOwnerChangeHistory(
        ChangeAction="ADDED",
        OwningUser=person_org,
        OwningApplication=app,
    )

    # === Units ===
    length_unit = model.createIfcSIUnit(UnitType="LENGTHUNIT", Name="METRE")
    area_unit = model.createIfcSIUnit(UnitType="AREAUNIT", Name="SQUARE_METRE")
    volume_unit = model.createIfcSIUnit(UnitType="VOLUMEUNIT", Name="CUBIC_METRE")
    unit_assignment = model.createIfcUnitAssignment([length_unit, area_unit, volume_unit])

    # === Project ===
    project = model.createIfcProject(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name="AI_Arhitector Project",
        UnitsInContext=unit_assignment,
    )

    # === Site ===
    site = model.createIfcSite(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name="Building Site",
    )
    model.createIfcRelAggregates(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        RelatingObject=project,
        RelatedObjects=[site],
    )

    # === Building ===
    building = model.createIfcBuilding(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name=f"{mat.title()} Building {floors}F",
        BuildingAddress=None,
    )
    model.createIfcRelAggregates(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        RelatingObject=site,
        RelatedObjects=[building],
    )

    # === Materials ===
    material = model.createIfcMaterial(mat.title())

    # === Этажи и стены ===
    all_storeys = []

    for floor_idx in range(floors):
        z = floor_idx * fH

        # Местоположение этажа
        storey_placement = model.createIfcLocalPlacement(
            None,
            model.createIfcAxis2Placement3D(
                model.createIfcCartesianPoint((0.0, 0.0, z))
            ),
        )

        storey = model.createIfcBuildingStorey(
            ifcopenshell.guid.new(),
            OwnerHistory=owner_history,
            Name=f"Floor {floor_idx + 1}",
            ObjectPlacement=storey_placement,
            Elevation=z,
        )
        all_storeys.append(storey)

        # Стены (4 штуки)
        walls_data = [
            ("Front", (0, -L / 2), W, "Y"),
            ("Back", (0, L / 2), W, "Y"),
            ("Left", (-W / 2, 0), L, "X"),
            ("Right", (W / 2, 0), L, "X"),
        ]

        for wall_name, (cx, cy), length, orientation in walls_data:
            _create_wall(
                model, owner_history, storey, material,
                wall_name, cx, cy, z, length, fH, thick, orientation,
            )

        # Окна (передняя и задняя стены)
        n_win = max(2, W // 3)
        for i in range(n_win):
            x = -W / 2 + (i + 1) * W / (n_win + 1)
            for wy, wall_dir in [(-L / 2 - thick / 2, "Front"), (L / 2 + thick / 2, "Back")]:
                _create_window(
                    model, owner_history, storey, material,
                    f"Window_{wall_dir}_{floor_idx}_{i}",
                    x, wy, z + fH * 0.3, 1.2, 1.5,
                )

        # Дверь (первый этаж, передняя стена)
        if floor_idx == 0:
            _create_door(
                model, owner_history, storey, material,
                "MainDoor", 0, -L / 2 - thick / 2, z, 0.9, 2.1,
            )

        # Плита перекрытия (не на первом этаже)
        if floor_idx > 0:
            _create_slab(
                model, owner_history, storey, material,
                f"Slab_{floor_idx}", 0, 0, z, W, L, 0.2,
            )

    # Привязать этажи к зданию
    model.createIfcRelAggregates(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        RelatingObject=building,
        RelatedObjects=all_storeys,
    )

    # === Помещения (IfcSpace) ===
    _create_rooms(model, owner_history, all_storeys, W, L, fH, params)

    # === Кровля ===
    total_h = floors * fH
    _create_roof(model, owner_history, building, material, W, L, total_h, roof_type)

    # Сохранение
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    model.write(output_path)

    return output_path


def _create_wall(model, owner_history, storey, material,
                 name, cx, cy, z, length, height, thick, orientation):
    """Создаёт IfcWall с позиционированием."""
    placement = model.createIfcLocalPlacement(
        storey.ObjectPlacement,
        model.createIfcAxis2Placement3D(
            model.createIfcCartesianPoint((cx, cy, z + height / 2))
        ),
    )

    # Простая box-репрезентация
    if orientation == "X":
        dx, dy, dz = thick, length, height
    else:
        dx, dy, dz = length, thick, height

    body = model.createIfcExtrudedAreaSolid(
        model.createIfcRectangleProfileDef(
            "AREA", None,
            model.createIfcAxis2Placement2D(
                model.createIfcCartesianPoint((0.0, 0.0))
            ),
            dx, dy,
        ),
        model.createIfcCartesianPoint((0.0, 0.0, -dz / 2)),
        model.createIfcDirection((0.0, 0.0, 1.0)),
        dz,
    )

    rep = model.createIfcShapeRepresentation(
        model.createIfcRepresentationContext(None, None, None),
        "Body", "SweptSolid", [body],
    )

    wall = model.createIfcWall(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name=name,
        ObjectPlacement=placement,
        Representation=model.createIfcProductDefinitionShape(None, None, [rep]),
    )

    # Material association
    model.createIfcRelAssociatesMaterial(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        RelatedObjects=[wall],
        RelatingMaterial=material,
    )


def _create_window(model, owner_history, storey, material,
                   name, x, y, z, width, height):
    """Создаёт IfcWindow."""
    placement = model.createIfcLocalPlacement(
        storey.ObjectPlacement,
        model.createIfcAxis2Placement3D(
            model.createIfcCartesianPoint((x, y, z + height / 2))
        ),
    )

    body = model.createIfcExtrudedAreaSolid(
        model.createIfcRectangleProfileDef(
            "AREA", None,
            model.createIfcAxis2Placement2D(
                model.createIfcCartesianPoint((0.0, 0.0))
            ),
            width, 0.05,
        ),
        model.createIfcCartesianPoint((0.0, 0.0, -height / 2)),
        model.createIfcDirection((0.0, 0.0, 1.0)),
        height,
    )

    rep = model.createIfcShapeRepresentation(
        model.createIfcRepresentationContext(None, None, None),
        "Body", "SweptSolid", [body],
    )

    window = model.createIfcWindow(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name=name,
        ObjectPlacement=placement,
        Representation=model.createIfcProductDefinitionShape(None, None, [rep]),
        OverallWidth=width,
        OverallHeight=height,
    )

    model.createIfcRelAssociatesMaterial(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        RelatedObjects=[window],
        RelatingMaterial=material,
    )


def _create_door(model, owner_history, storey, material,
                 name, x, y, z, width, height):
    """Создаёт IfcDoor."""
    placement = model.createIfcLocalPlacement(
        storey.ObjectPlacement,
        model.createIfcAxis2Placement3D(
            model.createIfcCartesianPoint((x, y, z + height / 2))
        ),
    )

    body = model.createIfcExtrudedAreaSolid(
        model.createIfcRectangleProfileDef(
            "AREA", None,
            model.createIfcAxis2Placement2D(
                model.createIfcCartesianPoint((0.0, 0.0))
            ),
            width, 0.08,
        ),
        model.createIfcCartesianPoint((0.0, 0.0, -height / 2)),
        model.createIfcDirection((0.0, 0.0, 1.0)),
        height,
    )

    rep = model.createIfcShapeRepresentation(
        model.createIfcRepresentationContext(None, None, None),
        "Body", "SweptSolid", [body],
    )

    door = model.createIfcDoor(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name=name,
        ObjectPlacement=placement,
        Representation=model.createIfcProductDefinitionShape(None, None, [rep]),
        OverallWidth=width,
        OverallHeight=height,
    )

    model.createIfcRelAssociatesMaterial(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        RelatedObjects=[door],
        RelatingMaterial=material,
    )


def _create_slab(model, owner_history, storey, material,
                 name, x, y, z, width, length, thickness):
    """Создаёт IfcSlab (плита перекрытия)."""
    placement = model.createIfcLocalPlacement(
        storey.ObjectPlacement,
        model.createIfcAxis2Placement3D(
            model.createIfcCartesianPoint((x, y, z))
        ),
    )

    body = model.createIfcExtrudedAreaSolid(
        model.createIfcRectangleProfileDef(
            "AREA", None,
            model.createIfcAxis2Placement2D(
                model.createIfcCartesianPoint((0.0, 0.0))
            ),
            width, length,
        ),
        model.createIfcCartesianPoint((0.0, 0.0, -thickness / 2)),
        model.createIfcDirection((0.0, 0.0, 1.0)),
        thickness,
    )

    rep = model.createIfcShapeRepresentation(
        model.createIfcRepresentationContext(None, None, None),
        "Body", "SweptSolid", [body],
    )

    slab = model.createIfcSlab(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name=name,
        ObjectPlacement=placement,
        Representation=model.createIfcProductDefinitionShape(None, None, [rep]),
        PredefinedType="FLOOR",
    )

    model.createIfcRelAssociatesMaterial(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        RelatedObjects=[slab],
        RelatingMaterial=material,
    )


def _create_roof(model, owner_history, building, material, W, L, total_h, roof_type):
    """Создаёт IfcRoof."""
    placement = model.createIfcLocalPlacement(
        building.ObjectPlacement,
        model.createIfcAxis2Placement3D(
            model.createIfcCartesianPoint((0.0, 0.0, total_h))
        ),
    )

    if roof_type == "flat":
        body = model.createIfcExtrudedAreaSolid(
            model.createIfcRectangleProfileDef(
                "AREA", None,
                model.createIfcAxis2Placement2D(
                    model.createIfcCartesianPoint((0.0, 0.0))
                ),
                W + 0.6, L + 0.6,
            ),
            model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            model.createIfcDirection((0.0, 0.0, 1.0)),
            0.2,
        )
    else:
        # Упрощённая двускатная кровля — как extruded triangle
        rh = 2.5
        body = model.createIfcExtrudedAreaSolid(
            model.createIfcArbitraryClosedProfileDef(
                "AREA", None,
                model.createIfcPolyline([
                    model.createIfcCartesianPoint((-W / 2 - 0.3, 0.0)),
                    model.createIfcCartesianPoint((0.0, rh)),
                    model.createIfcCartesianPoint((W / 2 + 0.3, 0.0)),
                    model.createIfcCartesianPoint((-W / 2 - 0.3, 0.0)),
                ]),
            ),
            model.createIfcCartesianPoint((0.0, -L / 2 - 0.3, 0.0)),
            model.createIfcDirection((0.0, 1.0, 0.0)),
            L + 0.6,
        )

    rep = model.createIfcShapeRepresentation(
        model.createIfcRepresentationContext(None, None, None),
        "Body", "SweptSolid", [body],
    )

    roof = model.createIfcRoof(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name="Roof",
        ObjectPlacement=placement,
        Representation=model.createIfcProductDefinitionShape(None, None, [rep]),
        PredefinedType="USERDEFINED",
    )

    model.createIfcRelAssociatesMaterial(
        ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        RelatedObjects=[roof],
        RelatingMaterial=material,
    )


def _create_rooms(model, owner_history, storeys, W, L, fH, params):
    """Создаёт IfcSpace (помещения) на каждом этаже."""
    rooms_data = _get_default_rooms(params)

    for floor_idx, storey in enumerate(storeys):
        floor_rooms = [r for r in rooms_data if r.get("floor", 1) == floor_idx + 1]
        if not floor_rooms and floor_idx == 0:
            # Дефолтные помещения для первого этажа
            floor_rooms = [
                {"name": "Living Room", "x": -W / 4, "y": 0, "w": W / 2, "d": L / 2},
                {"name": "Kitchen", "x": W / 4, "y": 0, "w": W / 2, "d": L / 2},
            ]

        for room in floor_rooms:
            rx = room.get("x", 0)
            ry = room.get("y", 0)
            rw = room.get("w", 4)
            rd = room.get("d", 4)

            placement = model.createIfcLocalPlacement(
                storey.ObjectPlacement,
                model.createIfcAxis2Placement3D(
                    model.createIfcCartesianPoint((rx, ry, 0))
                ),
            )

            body = model.createIfcExtrudedAreaSolid(
                model.createIfcRectangleProfileDef(
                    "AREA", None,
                    model.createIfcAxis2Placement2D(
                        model.createIfcCartesianPoint((0.0, 0.0))
                    ),
                    rw, rd,
                ),
                model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
                model.createIfcDirection((0.0, 0.0, 1.0)),
                fH,
            )

            rep = model.createIfcShapeRepresentation(
                model.createIfcRepresentationContext(None, None, None),
                "Body", "SweptSolid", [body],
            )

            space = model.createIfcSpace(
                ifcopenshell.guid.new(),
                OwnerHistory=owner_history,
                Name=room.get("name", "Room"),
                ObjectPlacement=placement,
                Representation=model.createIfcProductDefinitionShape(None, None, [rep]),
                PredefinedType="INTERNAL",
                CompositionElement=None,
            )

            # Площадь помещения
            area = rw * rd
            pset = model.createIfcPropertySet(
                ifcopenshell.guid.new(),
                OwnerHistory=owner_history,
                Name="Pset_SpaceCommon",
                HasProperties=[
                    model.createIfcPropertySingleValue(
                        "NetFloorArea", "AreaMeasure", area
                    ),
                    model.createIfcPropertySingleValue(
                        "NetVolume", "VolumeMeasure", area * fH
                    ),
                ],
            )
            model.createIfcRelDefinesByProperties(
                ifcopenshell.guid.new(),
                OwnerHistory=owner_history,
                RelatedObjects=[space],
                RelatingPropertyDefinition=pset,
            )


def _get_default_rooms(params: dict) -> list:
    """Возвращает список помещений по умолчанию."""
    W = params.get("width", 10)
    L = params.get("length", 12)
    return [
        {"name": "Living Room", "floor": 1, "x": -W / 4, "y": 0, "w": W / 2, "d": L / 2},
        {"name": "Kitchen", "floor": 1, "x": W / 4, "y": 0, "w": W / 2, "d": L / 2},
        {"name": "Hallway", "floor": 1, "x": 0, "y": -L / 4, "w": W / 3, "d": L / 4},
        {"name": "Master Bedroom", "floor": 2, "x": -W / 4, "y": 0, "w": W / 2, "d": L / 2},
        {"name": "Bedroom 2", "floor": 2, "x": W / 4, "y": 0, "w": W / 2, "d": L / 2},
        {"name": "Bathroom", "floor": 2, "x": 0, "y": -L / 4, "w": W / 4, "d": L / 4},
    ]
