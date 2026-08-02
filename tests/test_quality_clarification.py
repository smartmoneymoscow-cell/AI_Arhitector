"""
tests/test_quality_clarification.py — Tests for quality control and clarification.

v9.0 — Tests for multi-level quality checks, clarification, and agent isolation.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestQualityAgent:
    """Test quality_agent.py multi-level checks."""

    def test_resolution_map_includes_16k(self):
        """Quality agent should have 16K in its resolution map."""
        from shared.agents.quality_agent import QualityAgent
        agent = QualityAgent()
        assert "16k" in agent.MIN_RESOLUTIONS
        assert agent.MIN_RESOLUTIONS["16k"] == (15360, 8640)

    def test_resolution_map_includes_all_levels(self):
        """Quality agent should support all quality levels."""
        from shared.agents.quality_agent import QualityAgent
        agent = QualityAgent()
        for level in ["preview", "standard", "high", "ultra", "16k"]:
            assert level in agent.MIN_RESOLUTIONS

    def test_file_size_thresholds(self):
        """File size thresholds should be reasonable."""
        from shared.agents.quality_agent import QualityAgent
        agent = QualityAgent()
        assert agent.MIN_FILE_SIZES["16k"] >= 8_000_000  # 8MB minimum for 16K
        assert agent.MIN_FILE_SIZES["standard"] >= 100_000  # 100KB for 4K


class TestClarification:
    """Test clarification.py."""

    def test_engine_creates_questions_for_vague_prompt(self):
        """Vague prompts should trigger clarification."""
        from shared.clarification import ClarificationEngine
        engine = ClarificationEngine()
        result = engine.analyze("построй что-нибудь", {}, confidence=0.2)
        assert result.needs_clarification is True
        assert len(result.questions) > 0

    def test_engine_skips_for_confident_parse(self):
        """High-confidence parses should not trigger clarification."""
        from shared.clarification import ClarificationEngine
        engine = ClarificationEngine()
        result = engine.analyze(
            "двухэтажный кирпичный дом 10x12",
            {"object_type": "building", "building_type": "house", "floors": 2, "material": "brick"},
            confidence=0.9
        )
        # May still ask about optional fields, but fewer questions
        assert len(result.questions) <= 2

    def test_engine_has_visual_options(self):
        """Engine should be able to generate visual options."""
        from shared.clarification import ClarificationEngine
        engine = ClarificationEngine()
        options = engine.generate_visual_options("material")
        assert len(options) > 0
        assert any(o.recommended for o in options)

    def test_engine_applies_answers(self):
        """Engine should apply user answers to params."""
        from shared.clarification import ClarificationEngine
        engine = ClarificationEngine()
        result = engine.apply_answers({}, {"material": "кирпич", "floors": "3"})
        assert result["material"] == "brick"
        assert result["floors"] == 3

    def test_engine_has_all_option_types(self):
        """Engine should have visual options for key decision points."""
        from shared.clarification import ClarificationEngine
        engine = ClarificationEngine()
        for field in ["material", "roof_type", "foundation_type", "style", "landscape_style"]:
            options = engine.generate_visual_options(field)
            assert len(options) >= 2, f"Field {field} should have at least 2 options"


class TestAgentIsolation:
    """Test that agents are properly isolated."""

    def test_runner_has_fallback_for_all_agents(self):
        """AgentRunner should have fallback data for all non-critical agents."""
        from shared.agents.runner import AgentRunner
        runner = AgentRunner()
        for agent_name in runner.AGENT_CLASSES:
            if agent_name not in runner.CRITICAL_AGENTS:
                assert agent_name in runner.FALLBACK_DATA, f"Missing fallback for {agent_name}"

    def test_critical_agents_listed(self):
        """Only parser and geometry should be critical."""
        from shared.agents.runner import AgentRunner
        runner = AgentRunner()
        assert "parser" in runner.CRITICAL_AGENTS
        assert "geometry" in runner.CRITICAL_AGENTS

    def test_runner_has_all_agent_classes(self):
        """Runner should have class paths for all known agents."""
        from shared.agents.runner import AgentRunner
        runner = AgentRunner()
        expected_agents = [
            "parser", "geometry", "texture", "render", "export", "quality",
            "research", "market", "concept", "masterplan", "landscape",
            "brand", "financial", "presentation", "style", "lighting",
            "furniture", "mep", "structural", "compliance", "el", "mep_bim",
        ]
        for agent in expected_agents:
            assert agent in runner.AGENT_CLASSES, f"Missing agent class for {agent}"


class TestRouter:
    """Test router.py type detection."""

    def test_detect_type_landscape(self):
        """Router should detect landscape from LLM params."""
        from shared.router import _detect_type
        assert _detect_type("ландшафтный дизайн", {"object_type": "landscape"}) == "landscape"

    def test_detect_type_interior(self):
        """Router should detect interior from LLM params."""
        from shared.router import _detect_type
        assert _detect_type("ванная с джакузи", {"object_type": "interior", "room_type": "bathroom"}) == "interior"

    def test_detect_type_building(self):
        """Router should detect building from LLM params."""
        from shared.router import _detect_type
        assert _detect_type("дом 2 этажа", {"object_type": "building"}) == "building"

    def test_detect_type_interior_keywords_override(self):
        """Interior keywords should override building type."""
        from shared.router import _detect_type
        # "дизайн детской" should be interior even if object_type=building
        result = _detect_type("дизайн детской в классическом стиле", {"object_type": "building"})
        assert result == "interior"

    def test_detect_type_landscape_keywords(self):
        """Landscape keywords detected when LLM says landscape."""
        from shared.router import _detect_type
        result = _detect_type("ландшафтный дизайн участка с прудом", {"object_type": "landscape"})
        assert result == "landscape"

    def test_detect_type_landscape_keywords_fallback(self):
        """Landscape keywords as fallback when LLM doesn't set object_type."""
        from shared.router import _detect_type
        result = _detect_type("ландшафтный дизайн участка с прудом", {})
        assert result == "landscape"


class TestOrchestrator:
    """Test orchestrator.py pipeline."""

    def test_pipeline_profiles_complete(self):
        """All pipeline profiles should be defined."""
        from shared.agents.orchestrator import PIPELINE_PROFILES
        for profile in ["quick", "standard", "full", "premium", "interior", "landscape"]:
            assert profile in PIPELINE_PROFILES, f"Missing pipeline profile: {profile}"

    def test_landscape_profile_includes_landscape_agent(self):
        """Landscape pipeline should include landscape agent."""
        from shared.agents.orchestrator import PIPELINE_PROFILES
        assert "landscape" in PIPELINE_PROFILES["landscape"]

    def test_interior_profile_includes_furniture(self):
        """Interior pipeline should include furniture agent."""
        from shared.agents.orchestrator import PIPELINE_PROFILES
        assert "furniture" in PIPELINE_PROFILES["interior"]

    def test_premium_profile_includes_mep(self):
        """Premium pipeline should include MEP agent."""
        from shared.agents.orchestrator import PIPELINE_PROFILES
        assert "mep" in PIPELINE_PROFILES["premium"]

    def test_premium_profile_includes_structural(self):
        """Premium pipeline should include structural agent."""
        from shared.agents.orchestrator import PIPELINE_PROFILES
        assert "structural" in PIPELINE_PROFILES["premium"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
