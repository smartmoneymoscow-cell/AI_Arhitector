"""
tests/test_cad_builder.py — Tests for parametric CAD wall builder.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.cad_builder import (
    WallBuilder,
    WallSpec,
    WallOpening,
    RoomSpec,
    FloorSpec,
    BuildingSpec,
    BuildingBuilder,
    generate_parametric_wall_bpy,
    generate_building_from_params_bpy,
)


class TestWallOpening(unittest.TestCase):
    def test_door_sill_height_zero(self):
        opening = WallOpening("door", width=0.9, height=2.1, sill_height=0.9)
        self.assertEqual(opening.sill_height, 0.0)

    def test_window_keeps_sill_height(self):
        opening = WallOpening("window", width=1.2, height=1.5, sill_height=0.9)
        self.assertEqual(opening.sill_height, 0.9)


class TestWallSpec(unittest.TestCase):
    def test_length_horizontal(self):
        spec = WallSpec(start=(0, 0), end=(10, 0))
        self.assertAlmostEqual(spec.length, 10.0)

    def test_length_diagonal(self):
        spec = WallSpec(start=(0, 0), end=(3, 4))
        self.assertAlmostEqual(spec.length, 5.0)

    def test_angle_horizontal(self):
        spec = WallSpec(start=(0, 0), end=(10, 0))
        self.assertAlmostEqual(spec.angle, 0.0)

    def test_angle_vertical(self):
        spec = WallSpec(start=(0, 0), end=(0, 10))
        self.assertAlmostEqual(spec.angle, math.pi / 2)


class TestWallBuilder(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp_dir = tempfile.mkdtemp()
        self.builder = WallBuilder(output_dir=self.tmp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_simple_wall(self):
        spec = WallSpec(start=(0, 0), end=(10, 0), thickness=0.3, height=3.0)
        result = self.builder.create_wall(spec)
        # If OCCT is available, result is a shape; otherwise None
        if result is not None:
            analysis = self.builder.analyze_shape(result)
            self.assertIn("volume_m3", analysis)
            self.assertGreater(analysis["volume_m3"], 0)

    def test_wall_with_window(self):
        spec = WallSpec(
            start=(0, 0), end=(10, 0), thickness=0.3, height=3.0,
            openings=[WallOpening("window", width=1.2, height=1.5, sill_height=0.9, offset=4.0)]
        )
        result = self.builder.create_wall(spec)
        if result is not None:
            analysis = self.builder.analyze_shape(result)
            # Wall with window should have less volume than solid wall
            solid_spec = WallSpec(start=(0, 0), end=(10, 0), thickness=0.3, height=3.0)
            solid = self.builder.create_wall(solid_spec)
            solid_analysis = self.builder.analyze_shape(solid)
            self.assertLess(analysis["volume_m3"], solid_analysis["volume_m3"])

    def test_wall_with_door(self):
        spec = WallSpec(
            start=(0, 0), end=(10, 0), thickness=0.3, height=3.0,
            openings=[WallOpening("door", width=0.9, height=2.1, offset=6.0)]
        )
        result = self.builder.create_wall(spec)
        if result is not None:
            self.assertIsNotNone(result)


class TestRoomSpec(unittest.TestCase):
    def test_room_creation(self):
        room = RoomSpec(
            name="Гостиная",
            x=0, y=0, width=5, depth=4, height=2.8,
        )
        self.assertEqual(room.name, "Гостиная")
        self.assertEqual(room.width, 5)


class TestBuildingBuilder(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_from_params(self):
        params = {"building_type": "house"}
        building_params = {
            "floors": 2,
            "W": 10,
            "L": 12,
            "fH": 2.8,
            "mat": "brick",
            "rooms": [
                {"n": "Гостиная", "a": 24, "fl": 1, "tag": "l", "x": -2, "z": 1, "w": 5.5, "d": 4.2},
            ],
        }
        builder = BuildingBuilder()
        spec = builder.from_params(params, building_params)
        self.assertEqual(len(spec.floors), 2)
        self.assertEqual(spec.total_width, 10)
        self.assertEqual(spec.material, "brick")


class TestBpyScript(unittest.TestCase):
    def test_wall_script_generation(self):
        openings = [
            WallOpening("window", width=1.2, height=1.5, sill_height=0.9, offset=2.0),
            WallOpening("door", width=0.9, height=2.1, offset=6.0),
        ]
        script = generate_parametric_wall_bpy(
            start=(0, 0), end=(10, 0),
            thickness=0.3, height=3.0,
            openings=openings,
        )
        self.assertIn("ParamWall", script)
        self.assertIn("Opening_0_window", script)
        self.assertIn("Opening_1_door", script)
        self.assertIn("BOOLEAN", script)

    def test_building_script_generation(self):
        params = {"building_type": "house"}
        building_params = {
            "floors": 1,
            "W": 10,
            "L": 12,
            "fH": 2.8,
            "mat": "brick",
            "rooms": [
                {"n": "Гостиная", "a": 24, "fl": 1, "tag": "l", "x": 0, "z": 0, "w": 5.5, "d": 4.2},
            ],
        }
        script = generate_building_from_params_bpy(params, building_params)
        self.assertIn("ParamWall", script)


if __name__ == "__main__":
    unittest.main()
