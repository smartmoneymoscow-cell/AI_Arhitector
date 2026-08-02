"""
shared/omni_integration.py — Интеграция с mimo-omni для распознавания.

Обрабатывает:
    - Фото/сканы электрических зарисовок → структурированные данные
    - Фото интерьеров → определение стиля, мебели, материалов
    - Фото фасадов → определение стиля, материалов, конструктива
    - Планы БТИ → извлечение размеров, помещений

Использование:
    from shared.omni_integration import OmniEngine

    engine = OmniEngine()
    result = engine.recognize_sketch(image_url)
"""

import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

OMNI_API_URL = os.environ.get("OMNI_API_URL", "http://localhost:8083")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")


class OmniEngine:
    """Движок распознавания через mimo-omni API."""

    def recognize_sketch(self, image_source: str, task: str = "electrical") -> dict:
        """
        Распознавание зарисовки/фото.

        Args:
            image_source: URL или base64 изображения
            task: тип задачи (electrical/architectural/interior/floorplan)

        Returns:
            dict с распознанными элементами
        """
        prompts = {
            "electrical": (
                "Проанализируй эту электрическую зарисовку/схему. "
                "Определи: щиты, автоматы, розетки, выключатели, светильники, "
                "кабельные трассы, распределительные коробки. "
                "Верни JSON: {elements: [{type, location, connections}], "
                "cable_routes: [{from, to, cable_type}], single_line: {...}}"
            ),
            "architectural": (
                "Проанализируй это архитектурное фото/зарисовку. "
                "Определи: тип здания, стиль, материалы фасада, этажность, "
                "окна, двери, кровлю, особенности. "
                "Верни JSON: {building_type, style, materials, floors, features}"
            ),
            "interior": (
                "Проанализируй это фото интерьера. "
                "Определи: стиль, мебель, отделку стен/пола/потолка, "
                "освещение, цветовую палитру. "
                "Верни JSON: {style, furniture: [{type, material, color}], "
                "walls, floor, ceiling, lighting, palette}"
            ),
            "floorplan": (
                "Проанализируй этот план БТИ/архитектурный план. "
                "Извлеки: помещения с размерами, стены, окна, двери, "
                "сантехнику, инженерные точки. "
                "Верни JSON: {rooms: [{name, width_m, length_m, area_m2}], "
                "walls: [{thickness_mm, material}], windows: [{width_m, height_m}], "
                "doors: [{width_m, type}]}"
            ),
        }

        prompt = prompts.get(task, prompts["architectural"])

        # Если URL — передаём напрямую
        if image_source.startswith("http"):
            image_content = {"type": "image_url", "image_url": {"url": image_source}}
        else:
            # base64
            if not image_source.startswith("data:"):
                image_source = f"data:image/jpeg;base64,{image_source}"
            image_content = {"type": "image_url", "image_url": {"url": image_source}}

        return self._call_vlm(prompt, image_content)

    def _call_vlm(self, prompt: str, image_content: dict) -> dict:
        """Вызов Vision Language Model через OpenRouter."""
        if not OPENROUTER_API_KEY:
            return {"status": "no_api_key", "message": "OPENROUTER_API_KEY не установлен"}

        # Каскад VLM моделей
        vlm_models = [
            "google/gemini-2.5-pro",
            "anthropic/claude-sonnet-4",
            "google/gemini-2.5-flash",
        ]

        for model in vlm_models:
            try:
                result = self._call_single_vlm(model, prompt, image_content)
                if result:
                    return {"status": "ok", "model": model, "data": result}
            except Exception as e:
                logger.warning(f"VLM {model} failed: {e}")
                continue

        return {"status": "all_models_failed", "message": "Все VLM модели недоступны"}

    def _call_single_vlm(self, model: str, prompt: str, image_content: dict) -> dict | None:
        """Вызов одной VLM модели."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        image_content,
                    ],
                }
            ],
            "max_tokens": 2000,
            "temperature": 0.1,
        }

        r = httpx.post(
            f"{OPENROUTER_BASE}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )

        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            return self._extract_json(content)
        return None

    def _extract_json(self, text: str) -> dict | None:
        """Извлечение JSON из ответа LLM."""
        import re

        md = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if md:
            try:
                return json.loads(md.group(1))
            except json.JSONDecodeError:
                pass

        depth, start = 0, -1
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        start = -1
        return None


# Глобальный экземпляр
_omni: OmniEngine | None = None


def get_omni() -> OmniEngine:
    global _omni
    if _omni is None:
        _omni = OmniEngine()
    return _omni
