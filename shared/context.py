"""
shared/context.py — Project context for multi-turn dialog.

Maintains conversation state across multiple requests,
enabling iterative modifications like:
  - "построй дом 10x12"
  - "добавь балкон на 2 этаже"
  - "измени стиль на модерн"
  - "увеличь кухню"

Usage:
    from shared.context import ProjectContext, ContextStore

    store = ContextStore()
    ctx = store.get_or_create(session_id)
    ctx.add_turn("построй дом", params, result)
    ctx = store.get(session_id)
    # ctx.history, ctx.current_params, ctx.current_model_url
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("archai.context")


@dataclass
class ConversationTurn:
    """One turn in the conversation."""

    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: float = field(default_factory=time.time)
    user_prompt: str = ""
    parsed_params: dict = field(default_factory=dict)
    gen_type: str = ""
    result: dict = field(default_factory=dict)
    model_url: Optional[str] = None
    ifc_url: Optional[str] = None
    render_url: Optional[str] = None
    confidence: float = 0.0
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "timestamp": self.timestamp,
            "user_prompt": self.user_prompt,
            "parsed_params": self.parsed_params,
            "gen_type": self.gen_type,
            "model_url": self.model_url,
            "ifc_url": self.ifc_url,
            "render_url": self.render_url,
            "confidence": self.confidence,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ProjectContext:
    """
    Full project context — accumulated state from all conversation turns.

    Enables the LLM to understand what was built and what to modify.
    """

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    turns: list[ConversationTurn] = field(default_factory=list)

    # Current state (from last successful turn)
    current_params: dict = field(default_factory=dict)
    current_building_params: dict = field(default_factory=dict)
    current_gen_type: str = ""
    current_model_url: Optional[str] = None
    current_ifc_url: Optional[str] = None
    current_render_url: Optional[str] = None
    current_compliance: dict = field(default_factory=dict)

    # Accumulated modifications
    modifications: list[str] = field(default_factory=list)

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def last_turn(self) -> Optional[ConversationTurn]:
        return self.turns[-1] if self.turns else None

    def add_turn(
        self,
        prompt: str,
        params: dict,
        result: dict,
        gen_type: str = "",
        confidence: float = 0.0,
        duration_ms: float = 0.0,
    ):
        """Add a new conversation turn and update current state."""
        turn = ConversationTurn(
            user_prompt=prompt,
            parsed_params=params,
            gen_type=gen_type,
            result=result,
            model_url=result.get("exports", {}).get("glb") or result.get("render", {}).get("output_path"),
            ifc_url=result.get("exports", {}).get("ifc"),
            render_url=result.get("render", {}).get("output_path"),
            confidence=confidence,
            duration_ms=duration_ms,
        )
        self.turns.append(turn)
        self.updated_at = time.time()

        # Update current state
        if result:
            self.current_params = params
            self.current_gen_type = gen_type or self.current_gen_type
            if turn.model_url:
                self.current_model_url = turn.model_url
            if turn.ifc_url:
                self.current_ifc_url = turn.ifc_url
            if turn.render_url:
                self.current_render_url = turn.render_url

        # Track modifications
        if len(self.turns) > 1:
            self.modifications.append(f"Turn {len(self.turns)}: {prompt[:100]}")

    def get_summary(self) -> str:
        """Generate a text summary for LLM context."""
        parts = []
        parts.append(f"Проект: {self.current_gen_type or 'не определён'}")
        parts.append(f"Всего шагов: {self.turn_count}")

        if self.current_params:
            p = self.current_params
            parts.append(f"Тип: {p.get('building_type', '?')}")
            parts.append(f"Размер: {p.get('width_m', '?')}x{p.get('length_m', '?')}м")
            parts.append(f"Этажей: {p.get('floors', '?')}")
            parts.append(f"Стиль: {p.get('style', '?')}")
            parts.append(f"Материал: {p.get('material', '?')}")

        if self.current_building_params:
            bp = self.current_building_params
            if bp.get("rooms"):
                room_names = [r.get("n", "") for r in bp["rooms"]]
                parts.append(f"Комнаты: {', '.join(room_names)}")

        if self.modifications:
            parts.append("Модификации:")
            for mod in self.modifications[-5:]:  # last 5
                parts.append(f"  - {mod}")

        if self.current_compliance:
            score = self.current_compliance.get("score", 0)
            parts.append(f"Соответствие нормам: {score:.0%}")

        return "\n".join(parts)

    def get_context_for_llm(self) -> dict:
        """
        Get context dict for LLM prompt enrichment.
        Includes only what's needed for modification decisions.
        """
        return {
            "session_id": self.session_id,
            "turn_count": self.turn_count,
            "current_params": self.current_params,
            "current_gen_type": self.current_gen_type,
            "current_model_url": self.current_model_url,
            "has_model": bool(self.current_model_url),
            "last_prompt": self.last_turn.user_prompt if self.last_turn else "",
            "modifications": self.modifications[-5:],
            "summary": self.get_summary(),
        }

    def to_dict(self) -> dict:
        """Full serialization."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turn_count": self.turn_count,
            "turns": [t.to_dict() for t in self.turns],
            "current_params": self.current_params,
            "current_gen_type": self.current_gen_type,
            "current_model_url": self.current_model_url,
            "current_ifc_url": self.current_ifc_url,
            "current_render_url": self.current_render_url,
            "current_compliance": self.current_compliance,
            "modifications": self.modifications,
        }


class ContextStore:
    """
    Stores project contexts (conversations).

    Backends: in-memory (default) or Redis.
    """

    def __init__(self, redis_url: str = ""):
        self._memory: dict[str, ProjectContext] = {}
        self._redis = None
        if redis_url:
            try:
                import redis

                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
                logger.info("ContextStore: Redis connected")
            except Exception as e:
                logger.warning("ContextStore: Redis unavailable (%s), using memory", e)
                self._redis = None

    def get_or_create(self, session_id: str | None = None) -> ProjectContext:
        """Get existing context or create new one."""
        if session_id:
            ctx = self.get(session_id)
            if ctx:
                return ctx

        ctx = ProjectContext(session_id=session_id or uuid.uuid4().hex[:12])
        self._memory[ctx.session_id] = ctx
        return ctx

    def get(self, session_id: str) -> Optional[ProjectContext]:
        """Get context by session_id."""
        # Memory
        if session_id in self._memory:
            return self._memory[session_id]

        # Redis
        if self._redis:
            try:
                raw = self._redis.get(f"context:{session_id}")
                if raw:
                    data = json.loads(raw)
                    ctx = self._deserialize(data)
                    self._memory[session_id] = ctx
                    return ctx
            except Exception as e:
                logger.warning("ContextStore Redis get failed: %s", e)

        return None

    def save(self, ctx: ProjectContext):
        """Save context."""
        self._memory[ctx.session_id] = ctx

        if self._redis:
            try:
                data = json.dumps(ctx.to_dict(), ensure_ascii=False, default=str)
                self._redis.setex(f"context:{ctx.session_id}", 86400 * 7, data)  # 7 days TTL
            except Exception as e:
                logger.warning("ContextStore Redis save failed: %s", e)

    def delete(self, session_id: str):
        """Delete context."""
        self._memory.pop(session_id, None)
        if self._redis:
            try:
                self._redis.delete(f"context:{session_id}")
            except Exception:
                pass

    def list_sessions(self, limit: int = 50) -> list[dict]:
        """List recent sessions."""
        sessions = []
        for ctx in sorted(self._memory.values(), key=lambda c: c.updated_at, reverse=True)[:limit]:
            sessions.append({
                "session_id": ctx.session_id,
                "turn_count": ctx.turn_count,
                "updated_at": ctx.updated_at,
                "current_gen_type": ctx.current_gen_type,
                "last_prompt": ctx.last_turn.user_prompt[:100] if ctx.last_turn else "",
            })
        return sessions

    def _deserialize(self, data: dict) -> ProjectContext:
        """Deserialize from dict."""
        ctx = ProjectContext(
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", 0),
            updated_at=data.get("updated_at", 0),
        )
        ctx.current_params = data.get("current_params", {})
        ctx.current_gen_type = data.get("current_gen_type", "")
        ctx.current_model_url = data.get("current_model_url")
        ctx.current_ifc_url = data.get("current_ifc_url")
        ctx.current_render_url = data.get("current_render_url")
        ctx.current_compliance = data.get("current_compliance", {})
        ctx.modifications = data.get("modifications", [])

        for turn_data in data.get("turns", []):
            turn = ConversationTurn(
                turn_id=turn_data.get("turn_id", ""),
                timestamp=turn_data.get("timestamp", 0),
                user_prompt=turn_data.get("user_prompt", ""),
                parsed_params=turn_data.get("parsed_params", {}),
                gen_type=turn_data.get("gen_type", ""),
                model_url=turn_data.get("model_url"),
                ifc_url=turn_data.get("ifc_url"),
                render_url=turn_data.get("render_url"),
                confidence=turn_data.get("confidence", 0),
                duration_ms=turn_data.get("duration_ms", 0),
            )
            ctx.turns.append(turn)

        return ctx


# ═══════════════════════════════════════════════════════════════
# PROMPT ENRICHMENT — inject context into LLM prompts
# ═══════════════════════════════════════════════════════════════


def enrich_prompt_with_context(prompt: str, ctx: ProjectContext) -> str:
    """
    Enrich user prompt with project context for LLM parsing.

    Transforms "добавь балкон" into contextual prompt that LLM
    can understand in relation to the existing building.
    """
    if ctx.turn_count == 0:
        return prompt

    summary = ctx.get_summary()
    last_params = ctx.current_params

    enriched = f"""Контекст проекта (предыдущие шаги):
{summary}

Текущие параметры: {json.dumps(last_params, ensure_ascii=False)}

Новый запрос пользователя: {prompt}

Учти контекст проекта при парсинге. Если пользователь говорит "добавь балкон" — 
это означает добавление к текущему зданию, а не создание нового.
Если "измени стиль" — модифицируй текущий стиль, сохранив остальные параметры.
"""
    return enriched


def detect_modification_intent(prompt: str, ctx: ProjectContext) -> dict:
    """
    Detect if the user wants to modify existing project or start new.

    Returns:
        {
            "is_modification": bool,
            "modification_type": str,  # add|remove|change|resize
            "target": str,  # what to modify
            "confidence": float,
        }
    """
    prompt_lower = prompt.lower()
    is_modification = False
    mod_type = ""
    target = ""

    # Modification keywords
    add_kw = ["добав", "добавь", "пристав", "пристрой", "расшир"]
    remove_kw = ["убери", "удали", "снес", "убрать"]
    change_kw = ["измени", "поменя", "замени", "сделай стиль", "пере"]
    resize_kw = ["увелич", "уменьш", "расширь", "сузь"]

    if ctx.turn_count > 0:
        if any(kw in prompt_lower for kw in add_kw):
            is_modification = True
            mod_type = "add"
        elif any(kw in prompt_lower for kw in remove_kw):
            is_modification = True
            mod_type = "remove"
        elif any(kw in prompt_lower for kw in change_kw):
            is_modification = True
            mod_type = "change"
        elif any(kw in prompt_lower for kw in resize_kw):
            is_modification = True
            mod_type = "resize"

    # Detect target
    target_kw = {
        "balcony": ["балкон", "балконч"],
        "terrace": ["террас", "терасс"],
        "garage": ["гараж"],
        "floor": ["этаж", "этажн"],
        "room": ["комнат", "помещен"],
        "roof": ["крыш", "кровл"],
        "window": ["окно", "окна", "остеклен"],
        "door": ["двер"],
        "style": ["стиль", "дизайн"],
        "material": ["материал", "облицовк"],
        "kitchen": ["кухн"],
        "bathroom": ["ванн", "санузл"],
        "bedroom": ["спальн"],
        "living": ["гостин"],
    }

    for t, keywords in target_kw.items():
        if any(kw in prompt_lower for kw in keywords):
            target = t
            break

    return {
        "is_modification": is_modification,
        "modification_type": mod_type,
        "target": target,
        "confidence": 0.8 if is_modification and target else 0.3 if is_modification else 0.0,
    }


# Global context store instance
_global_store: ContextStore | None = None


def get_context_store(redis_url: str = "") -> ContextStore:
    """Get or create global context store."""
    global _global_store
    if _global_store is None:
        _global_store = ContextStore(redis_url=redis_url)
    return _global_store
