"""
shared/agents/dialog_agent.py — Multi-turn dialog agent.

Handles iterative project modifications:
  - Detects modification intent ("добавь балкон", "измени стиль")
  - Enriches prompts with project context
  - Merges modification params with existing params
  - Returns updated generation plan

This agent runs BEFORE parser in the pipeline when session context exists.
"""

import logging
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger("archai.dialog_agent")


class DialogAgent(BaseAgent):
    """
    Multi-turn dialog agent.

    When a session context exists, this agent:
    1. Analyzes the new prompt for modification intent
    2. Enriches the prompt with project context
    3. Merges new params with existing params
    4. Returns the enriched prompt and merged params

    Output is consumed by the parser agent downstream.
    """

    name = "dialog"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            prompt = task.params.get("prompt", "")
            session_id = task.params.get("session_id", "")
            context_data = task.params.get("context", {})

            if not session_id and not context_data:
                # No context — pass through
                return TaskResult(
                    status=TaskStatus.DONE,
                    data={
                        "enriched_prompt": prompt,
                        "is_modification": False,
                        "merged_params": {},
                        "has_context": False,
                    },
                    duration_ms=(time.time() - start) * 1000,
                )

            # Load context
            from shared.context import (
                get_context_store,
                enrich_prompt_with_context,
                detect_modification_intent,
            )

            store = get_context_store()
            ctx = None

            if session_id:
                ctx = store.get(session_id)

            if ctx is None and context_data:
                # Reconstruct from passed context
                ctx = store.get_or_create(session_id)
                ctx.current_params = context_data.get("current_params", {})
                ctx.current_gen_type = context_data.get("current_gen_type", "")
                ctx.current_model_url = context_data.get("current_model_url")

            if ctx is None:
                return TaskResult(
                    status=TaskStatus.DONE,
                    data={
                        "enriched_prompt": prompt,
                        "is_modification": False,
                        "merged_params": {},
                        "has_context": False,
                    },
                    duration_ms=(time.time() - start) * 1000,
                )

            # Detect modification intent
            mod_intent = detect_modification_intent(prompt, ctx)

            # Enrich prompt with context
            enriched_prompt = enrich_prompt_with_context(prompt, ctx)

            # Merge params if modification
            merged_params = {}
            if mod_intent["is_modification"] and ctx.current_params:
                merged_params = self._merge_modification(
                    ctx.current_params,
                    ctx.current_building_params,
                    mod_intent,
                    prompt,
                )

            return TaskResult(
                status=TaskStatus.DONE,
                data={
                    "enriched_prompt": enriched_prompt,
                    "original_prompt": prompt,
                    "is_modification": mod_intent["is_modification"],
                    "modification_type": mod_intent.get("modification_type", ""),
                    "modification_target": mod_intent.get("target", ""),
                    "modification_confidence": mod_intent.get("confidence", 0),
                    "merged_params": merged_params,
                    "has_context": True,
                    "session_id": ctx.session_id,
                    "turn_count": ctx.turn_count,
                    "context_summary": ctx.get_summary(),
                },
                duration_ms=(time.time() - start) * 1000,
            )

        except Exception as e:
            logger.error("DialogAgent failed: %s", e, exc_info=True)
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _merge_modification(
        self,
        current_params: dict,
        current_building_params: dict,
        mod_intent: dict,
        prompt: str,
    ) -> dict:
        """
        Merge modification into existing params.

        Returns updated params dict.
        """
        import copy

        merged = copy.deepcopy(current_params)
        mod_type = mod_intent.get("modification_type", "")
        target = mod_intent.get("target", "")

        prompt_lower = prompt.lower()

        # Handle specific modifications
        if target == "balcony":
            features = merged.get("features", [])
            if mod_type == "add" and "balcony" not in features:
                features.append("balcony")
            elif mod_type == "remove":
                features = [f for f in features if f != "balcony"]
            merged["features"] = features

        elif target == "terrace":
            features = merged.get("features", [])
            if mod_type == "add" and "terrace" not in features:
                features.append("terrace")
            elif mod_type == "remove":
                features = [f for f in features if f != "terrace"]
            merged["features"] = features

        elif target == "garage":
            features = merged.get("features", [])
            if mod_type == "add" and "garage" not in features:
                features.append("garage")
            elif mod_type == "remove":
                features = [f for f in features if f != "garage"]
            merged["features"] = features

        elif target == "floor":
            # "добавь этаж" → floors + 1
            if mod_type == "add":
                merged["floors"] = merged.get("floors", 2) + 1
            elif mod_type == "remove" and merged.get("floors", 2) > 1:
                merged["floors"] = merged.get("floors", 2) - 1

        elif target == "style":
            # Extract style from prompt
            style_map = {
                "модерн": "modern", "современн": "modern",
                "классическ": "classic", "классик": "classic",
                "минимализм": "minimalist", "минималист": "minimalist",
                "лофт": "loft", "хайтек": "hitech", "hi-tech": "hitech",
                "скандинавск": "scandi", "прованс": "provence",
                "барокко": "baroque", "японск": "japanese",
            }
            for kw, style in style_map.items():
                if kw in prompt_lower:
                    merged["style"] = style
                    break

        elif target == "material":
            mat_map = {
                "кирпич": "brick", "дерев": "wood", "деревянн": "wood",
                "бетон": "concrete", "стекл": "glass",
                "штукатурк": "plaster", "камен": "stone",
                "металл": "metal", "пеноблок": "foam_block",
            }
            for kw, mat in mat_map.items():
                if kw in prompt_lower:
                    merged["material"] = mat
                    break

        elif target == "kitchen":
            if mod_type == "resize":
                # "увеличь кухню" → +20% area
                rooms = current_building_params.get("rooms", [])
                for room in rooms:
                    if room.get("tag") == "k":
                        factor = 1.2 if "увелич" in prompt_lower else 0.8
                        room["w"] = round(room.get("w", 3) * factor, 1)
                        room["d"] = round(room.get("d", 3) * factor, 1)
                        room["a"] = round(room["w"] * room["d"], 1)
                merged["_rooms_override"] = rooms

        elif target == "room":
            # Generic room addition
            if mod_type == "add":
                # Extract room type from prompt
                room_types = {
                    "спальн": ("bedroom", "s", 12),
                    "ванн": ("bathroom", "b", 6),
                    "кабинет": ("study", "s", 10),
                    "гардероб": ("wardrobe", "h", 5),
                    "кладов": ("storage", "h", 3),
                }
                for kw, (rtype, tag, min_area) in room_types.items():
                    if kw in prompt_lower:
                        merged["_add_room"] = {
                            "type": rtype,
                            "tag": tag,
                            "min_area": min_area,
                        }
                        break

        return merged
