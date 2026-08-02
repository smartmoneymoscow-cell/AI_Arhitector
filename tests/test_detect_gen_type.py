"""
tests/test_detect_gen_type.py — Tests for generation type detection.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _detect_gen_type(params: dict) -> str:
    """Copy of blender-service/app.py logic for testing.
    
    LLM is the source of truth. No keyword matching.
    """
    obj_type = (params.get("object_type") or "").strip().lower()
    room_type = (params.get("room_type") or "").strip().lower()
    building_type = (params.get("building_type") or "").strip().lower()

    # LLM is the source of truth
    if obj_type in ("interior", "room"):
        return "interior"
    if obj_type == "landscape":
        return "landscape"
    if obj_type == "building":
        return "building"
    if room_type:
        return "interior"
    if building_type == "landscape":
        return "landscape"
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

    def test_building_description_without_object_type(self):
        """If LLM didn't set object_type, description alone doesn't determine type."""
        # This is a fallback case — LLM should always set object_type
        assert _detect_gen_type({"building_description": "Дизайн кухни"}) == "building"

    def test_interior_from_description_with_object_type(self):
        """If LLM set object_type=interior, trust it."""
        assert _detect_gen_type({"object_type": "interior", "building_description": "Дизайн кухни"}) == "interior"

    def test_building_from_description_with_object_type(self):
        """If LLM set object_type=building, trust it even with interior keywords."""
        assert _detect_gen_type({"object_type": "building", "building_description": "Кухня ресторан"}) == "building"

    def test_hotel_is_building(self):
        assert _detect_gen_type({"object_type": "building", "building_type": "hotel"}) == "building"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
