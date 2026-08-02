"""
tests/test_trimesh_export.py — Tests for trimesh export module.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.trimesh_export import TrimeshExporter, TRIMESH_AVAILABLE


class TestTrimeshExporter(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.exporter = TrimeshExporter(output_dir=self.tmp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @unittest.skipUnless(TRIMESH_AVAILABLE, "trimesh not installed")
    def test_export_box_glb(self):
        path = self.exporter.export_box_to_glb(width=10, length=12, height=6)
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(".glb"))
        self.assertGreater(os.path.getsize(path), 0)

    @unittest.skipUnless(TRIMESH_AVAILABLE, "trimesh not installed")
    def test_export_box_with_color(self):
        path = self.exporter.export_box_to_glb(
            width=5, length=5, height=3,
            color=(1.0, 0.0, 0.0, 1.0)
        )
        self.assertIsNotNone(path)

    @unittest.skipUnless(TRIMESH_AVAILABLE, "trimesh not installed")
    def test_export_building_glb(self):
        building_params = {
            "W": 10,
            "L": 12,
            "floors": 2,
            "fH": 2.8,
            "mat": "brick",
            "roof": "flat",
            "rooms": [
                {"n": "Гостиная", "a": 24, "fl": 1, "tag": "l", "x": -2, "z": 1, "w": 5.5, "d": 4.2},
                {"n": "Кухня", "a": 14, "fl": 1, "tag": "k", "x": 3.5, "z": 1, "w": 3.5, "d": 3.5},
            ],
        }
        path = self.exporter.export_building_to_glb(building_params)
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path))

    def test_export_floorplan_svg(self):
        building_params = {
            "W": 10,
            "L": 12,
            "rooms": [
                {"n": "Гостиная", "a": 24, "fl": 1, "tag": "l", "x": -2, "z": 1, "w": 5.5, "d": 4.2},
                {"n": "Кухня", "a": 14, "fl": 1, "tag": "k", "x": 3.5, "z": 1, "w": 3.5, "d": 3.5},
            ],
        }
        path = self.exporter.export_floorplan_to_svg(building_params)
        self.assertIsNotNone(path)
        self.assertTrue(path.endswith(".svg"))
        with open(path) as f:
            content = f.read()
        self.assertIn("<svg", content)
        self.assertIn("Гостиная", content)


if __name__ == "__main__":
    unittest.main()
