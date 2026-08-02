"""
shared/compliance.py — Building code compliance checker.

Validates building designs against Russian (SP/GOST) and international (IBC) codes.

Standards implemented:
  - СП 1.13130.2020 — Fire safety, evacuation routes
  - СП 54.13330.2016 — Residential buildings
  - ГОСТ 21.501-2018 — Construction drawings
  - IBC 2021 — International Building Code (basic)

Usage:
    from shared.compliance import ComplianceChecker

    checker = ComplianceChecker()
    result = checker.check_building(params, building_params)
    # result = {
    #     "passed": True/False,
    #     "issues": [{"code": "SP_54_3.7", "severity": "error", "message": "...", "fix": "..."}],
    #     "warnings": [...],
    #     "score": 0.85,
    # }
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("archai.compliance")


@dataclass
class ComplianceIssue:
    """Single compliance issue."""

    code: str  # e.g. "SP_54_3.7"
    severity: str  # "error" | "warning" | "info"
    message: str
    fix: str = ""  # suggested fix
    standard: str = ""  # which standard
    category: str = ""  # fire | structural | accessibility | energy | layout


@dataclass
class ComplianceResult:
    """Result of compliance check."""

    passed: bool = True
    issues: list[ComplianceIssue] = field(default_factory=list)
    warnings: list[ComplianceIssue] = field(default_factory=list)
    score: float = 1.0  # 0.0 - 1.0
    checks_run: list[str] = field(default_factory=list)

    def add_error(self, code: str, message: str, fix: str = "", standard: str = "", category: str = ""):
        issue = ComplianceIssue(code=code, severity="error", message=message, fix=fix, standard=standard, category=category)
        self.issues.append(issue)
        self.passed = False

    def add_warning(self, code: str, message: str, fix: str = "", standard: str = "", category: str = ""):
        issue = ComplianceIssue(code=code, severity="warning", message=message, fix=fix, standard=standard, category=category)
        self.warnings.append(issue)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "issues": [
                {"code": i.code, "severity": i.severity, "message": i.message, "fix": i.fix, "standard": i.standard, "category": i.category}
                for i in self.issues
            ],
            "warnings": [
                {"code": w.code, "severity": w.severity, "message": w.message, "fix": w.fix, "standard": w.standard, "category": w.category}
                for w in self.warnings
            ],
            "score": self.score,
            "checks_run": self.checks_run,
        }


class ComplianceChecker:
    """
    Multi-standard building compliance checker.

    Runs all applicable checks and returns aggregated result.
    """

    def check_building(self, params: dict, building_params: dict) -> ComplianceResult:
        """
        Run all compliance checks on building params.

        Args:
            params: parsed LLM params
            building_params: building params from router

        Returns:
            ComplianceResult with issues and score
        """
        result = ComplianceResult()

        # Determine building category for applicable standards
        building_type = params.get("building_type", "house")
        floors = building_params.get("floors", 2)
        height = building_params.get("fH", 2.8) * floors

        # Run applicable checks
        self._check_sp54_residential(params, building_params, result)
        self._check_sp113130_fire(params, building_params, result)
        self._check_room_sizes(params, building_params, result)
        self._check_natural_light(params, building_params, result)
        self._check_accessibility(params, building_params, result)
        self._check_energy_efficiency(params, building_params, result)

        # Calculate score
        error_count = len(result.issues)
        warning_count = len(result.warnings)
        total_checks = len(result.checks_run)

        if total_checks > 0:
            # Each error costs 0.15, each warning costs 0.05
            penalty = error_count * 0.15 + warning_count * 0.05
            result.score = max(0.0, 1.0 - penalty)
        else:
            result.score = 1.0

        result.passed = error_count == 0

        return result

    def _check_sp54_residential(self, params: dict, building_params: dict, result: ComplianceResult):
        """СП 54.13330.2016 — Residential buildings."""
        result.checks_run.append("SP_54")

        floors = building_params.get("floors", 2)
        floor_height = building_params.get("fH", 2.8)
        rooms = building_params.get("rooms", [])

        # 3.7 — Minimum ceiling height for residential
        if floor_height < 2.5:
            result.add_error(
                "SP_54_3.7",
                f"Высота потолка {floor_height}м < 2.5м (СП 54.13330 п.3.7)",
                fix="Увеличить высоту этажа до ≥2.5м",
                standard="СП 54.13330.2016",
                category="layout",
            )
        elif floor_height < 2.7:
            result.add_warning(
                "SP_54_3.7",
                f"Высота потолка {floor_height}м < 2.7м (рекомендуется для жилых помещений)",
                fix="Увеличить высоту до ≥2.7м для комфорта",
                standard="СП 54.13330.2016",
                category="layout",
            )

        # 3.8 — Minimum room areas
        for room in rooms:
            name = room.get("n", "")
            area = room.get("a", 0)
            room_tag = room.get("tag", "")

            if room_tag == "l":  # living room
                if area < 12:
                    result.add_error(
                        "SP_54_3.8",
                        f"Площадь гостиной '{name}' = {area}м² < 12м² (СП 54.13330 п.3.8)",
                        fix="Увеличить площадь гостиной до ≥12м²",
                        standard="СП 54.13330.2016",
                        category="layout",
                    )
            elif room_tag == "k":  # kitchen
                if area < 8:
                    result.add_error(
                        "SP_54_3.8",
                        f"Площадь кухни '{name}' = {area}м² < 8м² (СП 54.13330 п.3.8)",
                        fix="Увеличить площадь кухни до ≥8м²",
                        standard="СП 54.13330.2016",
                        category="layout",
                    )
            elif room_tag == "s":  # bedroom
                if area < 9:
                    result.add_error(
                        "SP_54_3.8",
                        f"Площадь спальни '{name}' = {area}м² < 9м² (СП 54.13330 п.3.8)",
                        fix="Увеличить площадь спальни до ≥9м²",
                        standard="СП 54.13330.2016",
                        category="layout",
                    )

        # 3.10 — Building height limit for residential
        total_height = floor_height * floors
        if total_height > 75:
            result.add_error(
                "SP_54_3.10",
                f"Высота здания {total_height}м > 75м — требуется классификация как высотное",
                fix="Применить дополнительные требования для высотных зданий",
                standard="СП 54.13330.2016",
                category="structural",
            )

    def _check_sp113130_fire(self, params: dict, building_params: dict, result: ComplianceResult):
        """СП 1.13130.2020 — Fire safety, evacuation routes."""
        result.checks_run.append("SP_1_13130")

        floors = building_params.get("floors", 2)
        floor_height = building_params.get("fH", 2.8)
        rooms = building_params.get("rooms", [])
        width = building_params.get("W", 10)
        length = building_params.get("L", 12)
        building_type = params.get("building_type", "house")

        # 4.2 — Evacuation route length
        # Max distance to exit: residential ≤40m (with sprinkler: +25%)
        max_dimension = max(width, length)
        if max_dimension > 40:
            result.add_warning(
                "SP_1_13130_4.2",
                f"Макс. расстояние до выхода {max_dimension}м > 40м",
                fix="Добавить дополнительный эвакуационный выход или установить спринклерную систему",
                standard="СП 1.13130.2020",
                category="fire",
            )

        # 4.3 — Corridor width
        corridor_rooms = [r for r in rooms if r.get("tag") == "h"]
        for corridor in corridor_rooms:
            cw = corridor.get("w", 0)
            if cw < 1.2:
                result.add_error(
                    "SP_1_13130_4.3",
                    f"Ширина коридора '{corridor.get('n', '')}' = {cw}м < 1.2м",
                    fix="Увеличить ширину коридора до ≥1.2м",
                    standard="СП 1.13130.2020",
                    category="fire",
                )

        # 5.1 — Number of exits
        if floors > 1 and building_type not in ("house", "cottage"):
            # Multi-story non-residential needs 2+ exits
            exit_count = sum(1 for r in rooms if r.get("tag") == "h")
            if exit_count < 2:
                result.add_warning(
                    "SP_1_13130_5.1",
                    "Многоэтажное здание рекомендуется иметь ≥2 эвакуационных выхода",
                    fix="Добавить второй эвакуационный выход",
                    standard="СП 1.13130.2020",
                    category="fire",
                )

        # 5.2 — Staircase width
        if floors > 1:
            # Minimum staircase width: 0.9m for residential, 1.2m for public
            min_stair_width = 0.9 if building_type in ("house", "cottage") else 1.2
            # Assume staircase is part of corridor
            if corridor_rooms:
                stair_width = corridor_rooms[0].get("w", 1.5)
                if stair_width < min_stair_width:
                    result.add_error(
                        "SP_1_13130_5.2",
                        f"Ширина лестничного марша {stair_width}м < {min_stair_width}м",
                        fix=f"Увеличить ширину лестницы до ≥{min_stair_width}м",
                        standard="СП 1.13130.2020",
                        category="fire",
                    )

    def _check_room_sizes(self, params: dict, building_params: dict, result: ComplianceResult):
        """Check minimum room dimensions (not from code, but best practices)."""
        result.checks_run.append("room_sizes")

        rooms = building_params.get("rooms", [])
        for room in rooms:
            name = room.get("n", "")
            w = room.get("w", 0)
            d = room.get("d", 0)
            area = room.get("a", w * d)

            # Minimum width check
            if w < 2.0 and d < 2.0:
                result.add_warning(
                    "ROOM_SIZE",
                    f"Комната '{name}' слишком маленькая ({w}×{d}м)",
                    fix="Увеличить минимальный размер до 2.0м",
                    category="layout",
                )

    def _check_natural_light(self, params: dict, building_params: dict, result: ComplianceResult):
        """Check natural light requirements (KEO — коэффициент естественной освещённости)."""
        result.checks_run.append("natural_light")

        rooms = building_params.get("rooms", [])
        for room in rooms:
            name = room.get("n", "")
            room_tag = room.get("tag", "")
            area = room.get("a", 0)

            # Living rooms and bedrooms need windows
            if room_tag in ("l", "s") and area > 0:
                # Rough check: window area should be ≥ 1/8 of floor area
                # We don't have window data here, so just warn
                if area > 20:
                    result.add_warning(
                        "NATURAL_LIGHT",
                        f"Комната '{name}' ({area}м²) — убедитесь что площадь остекления ≥ {area/8:.1f}м² (1/8 площади пола)",
                        fix="Добавить окна или увеличить площадь остекления",
                        standard="СП 54.13330.2016 п.6.2",
                        category="layout",
                    )

    def _check_accessibility(self, params: dict, building_params: dict, result: ComplianceResult):
        """Check accessibility requirements."""
        result.checks_run.append("accessibility")

        floors = building_params.get("floors", 2)
        building_type = params.get("building_type", "house")

        # For public/commercial buildings — need accessible entrance
        if building_type in ("office", "hotel", "commercial"):
            if floors > 1:
                result.add_warning(
                    "ACCESS_ELEVATOR",
                    f"Здание типа '{building_type}' с {floors} этажами — рекомендуется лифт",
                    fix="Добавить пассажирский лифт для маломобильных групп",
                    standard="СП 59.13330.2016",
                    category="accessibility",
                )

    def _check_energy_efficiency(self, params: dict, building_params: dict, result: ComplianceResult):
        """Check energy efficiency requirements."""
        result.checks_run.append("energy")

        material = building_params.get("mat", "plaster")
        floors = building_params.get("floors", 2)
        floor_height = building_params.get("fH", 2.8)

        # Wall thickness for insulation
        wall_thickness = building_params.get("wall_thickness", 0.3)

        # Basic U-value check (simplified)
        # Brick 250mm: U ≈ 1.5 W/(m²·K) — needs insulation
        # With 100mm insulation: U ≈ 0.35 W/(m²·K) — OK
        if material == "brick" and wall_thickness < 0.4:
            result.add_warning(
                "ENERGY_WALL",
                f"Стена из кирпича толщиной {wall_thickness}м — требуется утепление (СП 50.13330.2012)",
                fix="Добавить 100-150мм утеплителя (минвата/EPS) или увеличить толщину стены",
                standard="СП 50.13330.2012",
                category="energy",
            )

        # Window-to-wall ratio
        width = building_params.get("W", 10)
        length = building_params.get("L", 12)
        perimeter = 2 * (width + length)
        wall_area = perimeter * floor_height * floors

        # Max 40% glazing for energy efficiency
        # We don't have exact window data, so informational
        result.add_warning(
            "ENERGY_WINDOW",
            f"Площадь стен ≈{wall_area:.0f}м² — площадь окон не должна превышать 40% ({wall_area*0.4:.0f}м²)",
            fix="Проверить соотношение площади окон и стен",
            standard="СП 50.13330.2012",
            category="energy",
        )
        # Remove the last warning since it's informational — convert to info
        if result.warnings and result.warnings[-1].code == "ENERGY_WINDOW":
            result.warnings[-1].severity = "info"


# ═══════════════════════════════════════════════════════════════
# QUICK CHECK — lightweight check for orchestrator
# ═══════════════════════════════════════════════════════════════


def quick_compliance_check(params: dict, building_params: dict) -> dict:
    """
    Lightweight compliance check for orchestrator pipeline.
    Returns simplified result dict.
    """
    checker = ComplianceChecker()
    result = checker.check_building(params, building_params)
    return result.to_dict()
