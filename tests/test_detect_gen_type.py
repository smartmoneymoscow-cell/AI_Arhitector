"""
tests/test_detect_gen_type.py — Tests for generation type detection.

v9.0 — Expanded coverage for landscape, interior edge cases, and flexibility.
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
        assert _detect_gen_type({"building_description": "Дизайн кухни"}) == "building"

    def test_interior_from_description_with_object_type(self):
        """If LLM set object_type=interior, trust it."""
        assert _detect_gen_type({"object_type": "interior", "building_description": "Дизайн кухни"}) == "interior"

    def test_building_from_description_with_object_type(self):
        """If LLM set object_type=building, trust it even with interior keywords."""
        assert _detect_gen_type({"object_type": "building", "building_description": "Кухня ресторан"}) == "building"

    def test_hotel_is_building(self):
        assert _detect_gen_type({"object_type": "building", "building_type": "hotel"}) == "building"

    # ═══ NEW TESTS: landscape ═══

    def test_landscape_explicit(self):
        """Landscape should be detected when LLM says so."""
        assert _detect_gen_type({"object_type": "landscape"}) == "landscape"

    def test_landscape_with_features(self):
        """Landscape with pool/garden features."""
        assert _detect_gen_type({
            "object_type": "landscape",
            "features": ["pool", "garden"],
            "building_type": "landscape"
        }) == "landscape"

    def test_landscape_not_building(self):
        """Landscape request should NOT generate a building."""
        assert _detect_gen_type({"object_type": "landscape", "building_type": "landscape"}) == "landscape"

    # ═══ NEW TESTS: interior edge cases ═══

    def test_bathroom_interior(self):
        """Bathroom request should be interior."""
        assert _detect_gen_type({"object_type": "interior", "room_type": "bathroom"}) == "interior"

    def test_children_room_interior(self):
        """Children's room should be interior."""
        assert _detect_gen_type({"object_type": "interior", "room_type": "children"}) == "interior"

    def test_sauna_interior(self):
        """Sauna interior should be interior."""
        assert _detect_gen_type({"object_type": "interior", "room_type": "sauna"}) == "interior"

    def test_kitchen_hitech_interior(self):
        """Kitchen in hi-tech style should be interior."""
        assert _detect_gen_type({
            "object_type": "interior",
            "room_type": "kitchen",
            "style": "hitech"
        }) == "interior"

    # ═══ NEW TESTS: building types ═══

    def test_bathhouse_building(self):
        """Bathhouse (баня) should be building."""
        assert _detect_gen_type({"object_type": "building", "building_type": "bathhouse"}) == "building"

    def test_gazebo_building(self):
        """Gazebo should be building."""
        assert _detect_gen_type({"object_type": "building", "building_type": "gazebo"}) == "building"

    def test_garage_building(self):
        """Garage should be building."""
        assert _detect_gen_type({"object_type": "building", "building_type": "garage"}) == "building"

    def test_barn_building(self):
        """Barn should be building."""
        assert _detect_gen_type({"object_type": "building", "building_type": "barn"}) == "building"

    # ═══ NEW TESTS: validation flexibility ═══

    def test_unknown_object_type_fallback(self):
        """Unknown object_type should fallback to building."""
        assert _detect_gen_type({"object_type": "unknown_type"}) == "building"

    def test_empty_object_type_with_room_type(self):
        """Empty object_type but room_type set should be interior."""
        assert _detect_gen_type({"object_type": "", "room_type": "bedroom"}) == "interior"

    def test_none_object_type(self):
        """None object_type should fallback to building."""
        assert _detect_gen_type({"object_type": None}) == "building"


class TestValidation:
    """Test validation.py flexibility."""

    def _validate(self, params):
        from shared.validation import validate_params
        return validate_params(params)

    def test_accepts_unknown_building_type(self):
        """Validation should accept unknown building types from LLM."""
        result = self._validate({"building_type": "observatory", "object_type": "building"})
        assert result["building_type"] == "observatory"

    def test_accepts_unknown_style(self):
        """Validation should accept unknown styles from LLM."""
        result = self._validate({"style": "art_nouveau"})
        assert result["style"] == "art_nouveau"

    def test_accepts_unknown_material(self):
        """Validation should accept unknown materials from LLM."""
        result = self._validate({"material": "bamboo"})
        assert result["material"] == "bamboo"

    def test_accepts_unknown_room_type(self):
        """Validation should accept unknown room types from LLM."""
        result = self._validate({"room_type": "wine_cellar", "object_type": "interior"})
        assert result["room_type"] == "wine_cellar"

    def test_rejects_invalid_dimensions(self):
        """Should clamp invalid dimensions to minimum."""
        result = self._validate({"width_m": -5, "length_m": 0})
        assert result["width_m"] >= 0.5  # clamped to min
        assert result["length_m"] >= 0.5  # clamped to min

    def test_clamps_large_dimensions(self):
        """Should clamp unrealistically large dimensions."""
        result = self._validate({"width_m": 1000})
        assert result["width_m"] <= 500

    def test_preserves_confidence(self):
        """Should preserve confidence from LLM."""
        result = self._validate({"confidence": 0.85})
        assert result["confidence"] == 0.85

    def test_preserves_reasoning(self):
        """Should preserve reasoning from LLM."""
        result = self._validate({"reasoning": "User asked for a barn"})
        assert result["reasoning"] == "User asked for a barn"


class TestParserPrompt:
    """Test parser SYSTEM_PROMPT handles edge cases."""

    def test_prompt_includes_landscape_rules(self):
        """SYSTEM_PROMPT should mention landscape detection."""
        from shared.parser import SYSTEM_PROMPT
        assert "landscape" in SYSTEM_PROMPT.lower() or "ландшафт" in SYSTEM_PROMPT.lower()

    def test_prompt_includes_interior_rules(self):
        """SYSTEM_PROMPT should mention interior detection."""
        from shared.parser import SYSTEM_PROMPT
        assert "interior" in SYSTEM_PROMPT.lower() or "интерьер" in SYSTEM_PROMPT.lower()

    def test_prompt_version_updated(self):
        """Prompt version should be v9.0+."""
        from shared.parser import SYSTEM_PROMPT_VERSION
        assert SYSTEM_PROMPT_VERSION >= "v9.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
