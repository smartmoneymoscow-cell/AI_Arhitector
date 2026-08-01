"""
shared/agents/style_agent.py — Агент определения и применения стиля.

Отвечает за:
    - Определение стиля из промта
    - Определение стиля из референсного изображения
    - Применение стиля к генерируемой модели
    - Генерацию стайлгайда
"""

import logging
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class StyleAgent(BaseAgent):
    name = "style"

    STYLE_KEYWORDS = {
        "modern": ["современный", "модерн", "modern", "минималистичный", "чистые линии"],
        "классический": ["классический", "classic", "неоклассика", "колонны", "лепнина"],
        "лофт": ["лофт", "loft", "индустриальный", "кирпич", "открытые балки"],
        "минимализм": ["минимализм", "minimalist", "простота", "монохром"],
        "скандинавский": ["скандинавский", "scandinavian", "hygge", "светлое дерево"],
        "средиземноморский": ["средиземноморский", "mediterranean", "терракота", "арки"],
        "хай-тек": ["хай-тек", "hi-tech", "футуристический", "технологичный"],
        "барокко": ["барокко", "baroque", "роскошный", "вычурный"],
        "ар-деко": ["ар-деко", "art deco", "геометрия", "золото"],
        "японский": ["японский", "japanese", "дзен", "бамбук", "татами"],
        "прованс": ["прованс", "provence", "лаванда", "потёртый шик"],
        "биофильный": ["биофильный", "biophilic", "зелёные стены", "природа внутри"],
    }

    STYLE_PROPERTIES = {
        "modern": {
            "geometry": "четкие линии, плоские крыши, large glass",
            "palette": ["#FFFFFF", "#333333", "#E74C3C", "#3498DB"],
            "materials": ["стекло", "бетон", "сталь", "дерево"],
            "proportions": "горизонтальные акценты, open plan",
            "details": "минимум декора, скрытые ручки, панорамные окна",
        },
        "классический": {
            "geometry": "симметрия, двускатные крыши, колоннады",
            "palette": ["#F5F5DC", "#8B4513", "#DEB887", "#2F4F4F"],
            "materials": ["кирпич", "камень", "штукатурка", "черепица"],
            "proportions": "золотое сечение, вертикальные акценты",
            "details": "карнизы, молдинги, лепнина, рустовка",
        },
        "лофт": {
            "geometry": "открытые пространства, высокие потолки",
            "palette": ["#2C3E50", "#95A5A6", "#E74C3C", "#F39C12"],
            "materials": ["кирпич", "бетон", "сталь", "стекло"],
            "proportions": "свободная планировка, industrial scale",
            "details": "открытые трубы, балки, вентиляция",
        },
        "минимализм": {
            "geometry": "чистые геометрические формы",
            "palette": ["#FFFFFF", "#F5F5F5", "#E0E0E0", "#333333"],
            "materials": ["бетон", "стекло", "сталь"],
            "proportions": "квадратные пропорции, модульность",
            "details": "отсутствие декора, скрытые системы хранения",
        },
        "скандинавский": {
            "geometry": "простые формы, скатные крыши",
            "palette": ["#FFFFFF", "#F5DEB3", "#87CEEB", "#228B22"],
            "materials": ["дерево", "штукатурка", "стекло"],
            "proportions": "человеческий масштаб, уютные пропорции",
            "details": "большие окна, камин, натуральные текстуры",
        },
        "хай-тек": {
            "geometry": "динамические формы, нестандартные углы",
            "palette": ["#C0C0C0", "#1A1A1A", "#4169E1", "#E74C3C"],
            "materials": ["сталь", "стекло", "алюминий", "композиты"],
            "proportions": "вытянутые пропорции, динамические линии",
            "details": "LED-подсветка, панели сенсоров, скрытые механизмы",
        },
        "японский": {
            "geometry": "гармоничные пропорции, асимметрия",
            "palette": ["#F5F5DC", "#8B4513", "#228B22", "#2F2F2F"],
            "materials": ["дерево (кедр, бамбук)", "бумага (сёдзи)", "камень"],
            "proportions": "татами-модуль (90×180 см)",
            "details": "раздвижные перегородки, ниша токонома, сад камней",
        },
        "биофильный": {
            "geometry": "органические формы, плавные линии",
            "palette": ["#228B22", "#8B4513", "#F5DEB3", "#87CEEB"],
            "materials": ["дерево", "камень", "стекло", "зелёные стены"],
            "proportions": "природные пропорции, фрактальная геометрия",
            "details": "зелёные стены, внутренний двор, водные элементы",
        },
    }

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            source = params.get("source", "prompt")

            if source == "image":
                result = self._analyze_image_style(params)
            elif source == "reference":
                result = self._match_reference(params)
            else:
                result = self._detect_from_prompt(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=result,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"StyleAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _detect_from_prompt(self, params: dict) -> dict:
        """Определить стиль из текстового описания."""
        prompt = params.get("prompt", "").lower()

        # Подсчёт совпадений
        scores = {}
        for style, keywords in self.STYLE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in prompt)
            if score > 0:
                scores[style] = score

        # Если не нашли — modern по умолчанию
        if not scores:
            detected = "modern"
            confidence = 0.3
        else:
            detected = max(scores, key=scores.get)
            confidence = min(0.95, 0.5 + scores[detected] * 0.15)

        properties = self.STYLE_PROPERTIES.get(detected, self.STYLE_PROPERTIES["modern"])

        return {
            "type": "style_detection",
            "detected_style": detected,
            "confidence": confidence,
            "all_scores": scores,
            "properties": properties,
            "blender_params": self._to_blender_params(detected, properties),
            "recommendations": self._generate_style_recommendations(detected, properties),
        }

    def _analyze_image_style(self, params: dict) -> dict:
        """Анализ стиля из изображения (через LLM/mimo-omni)."""
        # Базовая реализация — возвращаем general analysis
        return {
            "type": "style_from_image",
            "detected_style": "modern",
            "confidence": 0.5,
            "note": "Для точного анализа изображений требуется интеграция с vision API",
            "properties": self.STYLE_PROPERTIES["modern"],
        }

    def _match_reference(self, params: dict) -> dict:
        """Подобрать стиль по референсному описанию."""
        description = params.get("description", "").lower()
        return self._detect_from_prompt({"prompt": description})

    def _to_blender_params(self, style: str, properties: dict) -> dict:
        """Параметры для Blender bpy-скрипта."""
        return {
            "material_colors": properties.get("palette", []),
            "primary_material": properties.get("materials", ["default"])[0],
            "geometry_type": "box" if style in ("минимализм", "modern") else "detailed",
            "roof_type": "flat" if style in ("modern", "минимализм", "хай-тек") else "gable",
            "window_style": "panoramic" if style in ("modern", "минимализм") else "traditional",
            "detail_level": "low" if style in ("минимализм") else "high",
        }

    def _generate_style_recommendations(self, style: str, properties: dict) -> list[str]:
        recs = []
        recs.append(f"Стиль: {style.title()}")
        recs.append(f"Геометрия: {properties.get('geometry', '—')}")
        recs.append(f"Материалы: {', '.join(properties.get('materials', []))}")
        recs.append(f"Детали: {properties.get('details', '—')}")
        return recs
