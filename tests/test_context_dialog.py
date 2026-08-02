"""
tests/test_context_dialog.py — Tests for multi-turn dialog context.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.context import (
    ProjectContext,
    ConversationTurn,
    ContextStore,
    enrich_prompt_with_context,
    detect_modification_intent,
)


class TestProjectContext(unittest.TestCase):
    def test_empty_context(self):
        ctx = ProjectContext()
        self.assertEqual(ctx.turn_count, 0)
        self.assertIsNone(ctx.last_turn)

    def test_add_turn(self):
        ctx = ProjectContext()
        ctx.add_turn(
            prompt="построй дом 10x12",
            params={"building_type": "house", "floors": 2},
            result={"exports": {"glb": "/path/model.glb"}},
            gen_type="building",
            confidence=0.9,
        )
        self.assertEqual(ctx.turn_count, 1)
        self.assertIsNotNone(ctx.last_turn)
        self.assertEqual(ctx.last_turn.user_prompt, "построй дом 10x12")
        self.assertEqual(ctx.current_gen_type, "building")
        self.assertEqual(ctx.current_model_url, "/path/model.glb")

    def test_multiple_turns_accumulate(self):
        ctx = ProjectContext()
        ctx.add_turn("построй дом", {"floors": 2}, {}, gen_type="building")
        ctx.add_turn("добавь балкон", {"features": ["balcony"]}, {}, gen_type="building")
        self.assertEqual(ctx.turn_count, 2)
        self.assertEqual(len(ctx.modifications), 1)

    def test_summary(self):
        ctx = ProjectContext()
        ctx.add_turn(
            "построй дом",
            {"building_type": "house", "width_m": 10, "length_m": 12, "floors": 2, "style": "modern", "material": "brick"},
            {"status": "done"},
            gen_type="building",
        )
        summary = ctx.get_summary()
        self.assertIn("building", summary)
        self.assertIn("10", summary)

    def test_context_for_llm(self):
        ctx = ProjectContext()
        ctx.add_turn("построй дом", {"building_type": "house"}, {}, gen_type="building")
        llm_ctx = ctx.get_context_for_llm()
        self.assertTrue(llm_ctx["has_model"] is False)
        self.assertEqual(llm_ctx["turn_count"], 1)

    def test_serialization(self):
        ctx = ProjectContext(session_id="test123")
        ctx.add_turn("test prompt", {"floors": 2}, {"result": True}, gen_type="building")
        data = ctx.to_dict()
        self.assertEqual(data["session_id"], "test123")
        self.assertEqual(data["turn_count"], 1)

        # Deserialize
        store = ContextStore()
        restored = store._deserialize(data)
        self.assertEqual(restored.session_id, "test123")
        self.assertEqual(restored.turn_count, 1)


class TestContextStore(unittest.TestCase):
    def test_get_or_create(self):
        store = ContextStore()
        ctx = store.get_or_create("session1")
        self.assertEqual(ctx.session_id, "session1")

        # Get same
        ctx2 = store.get_or_create("session1")
        self.assertEqual(ctx2.session_id, "session1")

    def test_get_nonexistent(self):
        store = ContextStore()
        ctx = store.get("nonexistent")
        self.assertIsNone(ctx)

    def test_save_and_get(self):
        store = ContextStore()
        ctx = store.get_or_create("test_save")
        ctx.add_turn("test", {}, {})
        store.save(ctx)

        loaded = store.get("test_save")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.turn_count, 1)

    def test_delete(self):
        store = ContextStore()
        ctx = store.get_or_create("to_delete")
        store.save(ctx)
        store.delete("to_delete")
        self.assertIsNone(store.get("to_delete"))

    def test_list_sessions(self):
        store = ContextStore()
        store.get_or_create("s1")
        store.get_or_create("s2")
        sessions = store.list_sessions()
        self.assertGreaterEqual(len(sessions), 2)


class TestModificationDetection(unittest.TestCase):
    def test_no_context_no_modification(self):
        ctx = ProjectContext()
        result = detect_modification_intent("построй дом", ctx)
        self.assertFalse(result["is_modification"])

    def test_add_balcony(self):
        ctx = ProjectContext()
        ctx.add_turn("построй дом", {}, {})
        result = detect_modification_intent("добавь балкон", ctx)
        self.assertTrue(result["is_modification"])
        self.assertEqual(result["modification_type"], "add")
        self.assertEqual(result["target"], "balcony")

    def test_change_style(self):
        ctx = ProjectContext()
        ctx.add_turn("построй дом", {}, {})
        result = detect_modification_intent("измени стиль на модерн", ctx)
        self.assertTrue(result["is_modification"])
        self.assertEqual(result["modification_type"], "change")
        self.assertEqual(result["target"], "style")

    def test_resize_kitchen(self):
        ctx = ProjectContext()
        ctx.add_turn("построй дом", {}, {})
        result = detect_modification_intent("увеличь кухню", ctx)
        self.assertTrue(result["is_modification"])
        self.assertEqual(result["modification_type"], "resize")
        self.assertEqual(result["target"], "kitchen")

    def test_new_project_no_modification(self):
        ctx = ProjectContext()  # No turns
        result = detect_modification_intent("добавь балкон", ctx)
        self.assertFalse(result["is_modification"])


class TestPromptEnrichment(unittest.TestCase):
    def test_no_context_returns_original(self):
        ctx = ProjectContext()
        enriched = enrich_prompt_with_context("построй дом", ctx)
        self.assertEqual(enriched, "построй дом")

    def test_with_context_enriches(self):
        ctx = ProjectContext()
        ctx.add_turn("построй дом 10x12", {"building_type": "house"}, {}, gen_type="building")
        enriched = enrich_prompt_with_context("добавь балкон", ctx)
        self.assertIn("добавь балкон", enriched)
        self.assertIn("Контекст проекта", enriched)


if __name__ == "__main__":
    unittest.main()
