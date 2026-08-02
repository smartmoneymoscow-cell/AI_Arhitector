"""
tests/test_detect_gen_type.py — Tests for generation type detection.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _detect_gen_type(params: dict) -> str:
    """Copy of blender-service/app.py logic for testing."""
    obj_type = (params.get("object_type") or "building").lower()
    room_type = (params.get("room_type") or "").lower()
    building_type = (params.get("building_type") or "").lower()

    if obj_type in ("interior", "room"):
        return "interior"
    if room_type:
        return "interior"
    if obj_type == "landscape" or building_type == "landscape":
        return "landscape"
    interior_keywords = ["кухн", "ванн", "спальн", "детск", "гостин", "интерьер", "дизайн"]
    description = (params.get("building_description") or "").lower()
    if any(kw in description for kw in interior_keywords):
        return "interior"
    return "building"


class TestDetectGenType:
    """Test _detect_gen_type function."""

    def test_explicit_interior(self):
        assert _detect_gen_type({"object_type": "interior"}) == "interior"

    def test_explicit_room(self):
        assert _detect_gen_type({"object_type": "room"}) == "interior"

    def test_room_type_set(self):
        assert _detect_gen_type({"room_type": "kitchen"}) == "interior"

    def test_explicit_landscape(self):
        assert _detect_gen_type({"object_type": "landscape"}) == "landscape"

    def test_building_type_landscape(self):
        assert _detect_gen_type({"building_type": "landscape"}) == "landscape"

    def test_building_default(self):
        assert _detect_gen_type({}) == "building"

    def test_building_explicit(self):
        assert _detect_gen_type({"object_type": "building"}) == "building"

    def test_interior_from_description_kitchen(self):
        assert _detect_gen_type({"building_description": "Дизайн кухни в стиле хайтек"}) == "interior"

    def test_interior_from_description_children(self):
        assert _detect_gen_type({"building_description": "Детская комната для мальчика"}) == "interior"

    def test_interior_from_description_bathroom(self):
        assert _detect_gen_type({"building_description": "Ванная с джакузи"}) == "interior"

    def test_building_from_description_house(self):
        assert _detect_gen_type({"building_description": "Двухэтажный кирпичный дом"}) == "building"

    def test_hotel_is_building(self):
        assert _detect_gen_type({"object_type": "building", "building_type": "hotel"}) == "building"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
