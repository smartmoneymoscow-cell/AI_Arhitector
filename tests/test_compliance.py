"""
tests/test_compliance.py — Tests for building compliance checker.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.compliance import ComplianceChecker, quick_compliance_check


class TestComplianceChecker(unittest.TestCase):
    def setUp(self):
        self.checker = ComplianceChecker()

    def test_valid_building_passes(self):
        params = {"building_type": "house"}
        building_params = {
            "floors": 2,
            "W": 10,
            "L": 12,
            "fH": 2.8,
            "mat": "brick",
            "wall_thickness": 0.4,
            "rooms": [
                {"n": "Гостиная", "a": 24, "fl": 1, "tag": "l", "x": -2, "z": 1, "w": 5.5, "d": 4.2},
                {"n": "Кухня", "a": 14, "fl": 1, "tag": "k", "x": 3.5, "z": 1, "w": 3.5, "d": 3.5},
                {"n": "Спальня", "a": 18, "fl": 2, "tag": "s", "x": -2, "z": 1, "w": 4.5, "d": 4},
            ],
        }
        result = self.checker.check_building(params, building_params)
        self.assertTrue(result.passed, f"Expected pass but got issues: {[i.message for i in result.issues]}")
        self.assertGreater(result.score, 0.5)
        self.assertIn("SP_54", result.checks_run)

    def test_low_ceiling_fails(self):
        params = {"building_type": "house"}
        building_params = {
            "floors": 2,
            "W": 10,
            "L": 12,
            "fH": 2.3,  # Too low!
            "mat": "brick",
            "rooms": [],
        }
        result = self.checker.check_building(params, building_params)
        self.assertFalse(result.passed)
        error_codes = [i.code for i in result.issues]
        self.assertIn("SP_54_3.7", error_codes)

    def test_small_kitchen_fails(self):
        params = {"building_type": "house"}
        building_params = {
            "floors": 1,
            "W": 10,
            "L": 12,
            "fH": 2.8,
            "mat": "brick",
            "rooms": [
                {"n": "Кухня", "a": 6, "fl": 1, "tag": "k", "x": 0, "z": 0, "w": 2, "d": 3},
            ],
        }
        result = self.checker.check_building(params, building_params)
        error_codes = [i.code for i in result.issues]
        self.assertIn("SP_54_3.8", error_codes)

    def test_small_living_room_fails(self):
        params = {"building_type": "house"}
        building_params = {
            "floors": 1,
            "W": 10,
            "L": 12,
            "fH": 2.8,
            "mat": "brick",
            "rooms": [
                {"n": "Гостиная", "a": 10, "fl": 1, "tag": "l", "x": 0, "z": 0, "w": 2.5, "d": 4},
            ],
        }
        result = self.checker.check_building(params, building_params)
        error_codes = [i.code for i in result.issues]
        self.assertIn("SP_54_3.8", error_codes)

    def test_narrow_corridor_fails(self):
        params = {"building_type": "office"}
        building_params = {
            "floors": 3,
            "W": 20,
            "L": 24,
            "fH": 3.2,
            "mat": "glass",
            "rooms": [
                {"n": "Коридор", "a": 5, "fl": 1, "tag": "h", "x": 0, "z": 0, "w": 1.0, "d": 5},
            ],
        }
        result = self.checker.check_building(params, building_params)
        error_codes = [i.code for i in result.issues]
        self.assertIn("SP_1_13130_4.3", error_codes)

    def test_energy_warning_for_thin_brick(self):
        params = {"building_type": "house"}
        building_params = {
            "floors": 1,
            "W": 10,
            "L": 12,
            "fH": 2.8,
            "mat": "brick",
            "wall_thickness": 0.25,  # Thin brick needs insulation
            "rooms": [],
        }
        result = self.checker.check_building(params, building_params)
        warning_codes = [w.code for w in result.warnings]
        self.assertIn("ENERGY_WALL", warning_codes)

    def test_quick_check_returns_dict(self):
        params = {"building_type": "house"}
        building_params = {
            "floors": 2,
            "W": 10,
            "L": 12,
            "fH": 2.8,
            "mat": "brick",
            "rooms": [],
        }
        result = quick_compliance_check(params, building_params)
        self.assertIsInstance(result, dict)
        self.assertIn("passed", result)
        self.assertIn("issues", result)
        self.assertIn("score", result)

    def test_score_calculation(self):
        params = {"building_type": "house"}
        building_params = {
            "floors": 2,
            "W": 10,
            "L": 12,
            "fH": 2.3,  # One error
            "mat": "brick",
            "wall_thickness": 0.25,  # One warning
            "rooms": [
                {"n": "Кухня", "a": 6, "fl": 1, "tag": "k", "x": 0, "z": 0, "w": 2, "d": 3},  # One error
            ],
        }
        result = self.checker.check_building(params, building_params)
        self.assertLess(result.score, 1.0)
        self.assertGreaterEqual(result.score, 0.0)


if __name__ == "__main__":
    unittest.main()
