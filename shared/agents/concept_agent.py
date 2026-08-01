"""
shared/agents/concept_agent.py — Агент концептуального дизайна.

Отвечает за:
    - Генерацию концепции проекта
    - Создание мудбордов
    - Определение архитектурного стиля
    - Формирование дизайн-концепции
"""

import time
import logging
from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class ConceptAgent(BaseAgent):
    name = "concept"

    # База знаний: стили → характеристики
    STYLE_DB = {
        "modern": {
            "keywords": ["чистые линии", "минимализм", "стекло", "бетон", "плоская крыша"],
            "materials": ["стекло", "бетон", "сталь", "дерево"],
            "colors": ["белый", "серый", "чёрный", "натуральное дерево"],
            "features": ["панорамные окна", "открытая планировка", "плоская крыша", "терраса"],
        },
        "классический": {
            "keywords": ["симметрия", "колонны", "карнизы", "лепнина", "двускатная крыша"],
            "materials": ["кирпич", "камень", "штукатурка"],
            "colors": ["бежевый", "белый", "терракотовый"],
            "features": ["колоннада", "эркер", "балюстрада", "мансарда"],
        },
        "лофт": {
            "keywords": ["открытые коммуникации", "кирпич", "бетон", "высокие потолки"],
            "materials": ["кирпич", "бетон", "сталь", "стекло"],
            "colors": ["серый", "кирпичный", "чёрный", "коричневый"],
            "features": ["открытые балки", "высокие окна", "металл в отделке"],
        },
        "скандинавский": {
            "keywords": ["уют", "светлое дерево", "белый", "функциональность"],
            "materials": ["дерево", "штукатурка", "стекло"],
            "colors": ["белый", "светлое дерево", "серый", "голубой"],
            "features": ["большие окна", "камин", "терраса", "зелёная крыша"],
        },
        "минимализм": {
            "keywords": ["пустота", "монохром", "геометрия", "функциональность"],
            "materials": ["бетон", "стекло", "сталь"],
            "colors": ["белый", "серый", "чёрный"],
            "features": ["скрытые двери", "встроенная мебель", "панорамное остекление"],
        },
        "биофильный": {
            "keywords": ["природа", "зелень", "свет", "воздух", "экология"],
            "materials": ["дерево", "камень", "стекло", "зелёные стены"],
            "colors": ["зелёный", "натуральное дерево", "белый", "земляные тона"],
            "features": ["зелёные стены", "внутренний двор", "зелёная крыша", "большие окна"],
        },
        "хай-тек": {
            "keywords": ["технологии", "сталь", "стекло", "геометрия", "футуризм"],
            "materials": ["сталь", "стекло", "алюминий", "композиты"],
            "colors": ["серебристый", "белый", "синий", "чёрный"],
            "features": ["солнечные панели", "умный дом", "динамическая подсветка"],
        },
    }

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            prompt = task.params.get("prompt", "")
            style = task.params.get("style", "modern")

            concept = self._generate_concept(prompt, style, task.params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=concept,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"ConceptAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _generate_concept(self, prompt: str, style: str, params: dict) -> dict:
        """Сгенерировать полную концепцию."""
        style_lower = style.lower()
        style_data = self.STYLE_DB.get(style_lower, self.STYLE_DB["modern"])

        building_type = params.get("building_type", "house")
        floors = params.get("floors", 2)
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)

        # Генерация концепции
        concept_name = self._generate_name(style, building_type)
        concept_description = self._generate_description(prompt, style_data, params)

        # Мудборд
        moodboard = self._create_moodboard(style_data, params)

        # Принципы дизайна
        design_principles = self._extract_principles(style_data, params)

        # Рекомендации
        recommendations = self._generate_recommendations(style_data, params)

        return {
            "type": "concept",
            "concept_name": concept_name,
            "style": style,
            "description": concept_description,
            "moodboard": moodboard,
            "design_principles": design_principles,
            "recommendations": recommendations,
            "material_palette": style_data["materials"],
            "color_palette": style_data["colors"],
            "key_features": style_data["features"],
            "keywords": style_data["keywords"],
        }

    def _generate_name(self, style: str, building_type: str) -> str:
        """Генерация названия концепции."""
        names = {
            "modern": ["Чистые линии", "Свет и пространство", "Современный минимализм"],
            "классический": ["Вечная элегантность", "Аристократический стиль", "Классическое величие"],
            "лофт": ["Индустриальный шарм", "Городской лофт", "Свободное пространство"],
            "минимализм": ["Форма и функция", "Чистое пространство", "Эссенция"],
            "биофильный": ["Живой дом", "Природа внутри", "Зелёный оазис"],
            "хай-тек": ["Технологии будущего", "Умный дом", "Футуристический дизайн"],
        }
        import random
        style_names = names.get(style.lower(), names["modern"])
        return random.choice(style_names)

    def _generate_description(self, prompt: str, style_data: dict, params: dict) -> str:
        """Генерация текстового описания концепции."""
        style = params.get("style", "modern")
        building_type = params.get("building_type", "house")
        floors = params.get("floors", 2)
        materials = ", ".join(style_data["materials"][:3])
        features = ", ".join(style_data["features"][:3])

        return (
            f"Концепция '{style}' для {building_type} ({floors} этаж.). "
            f"Основные материалы: {materials}. "
            f"Ключевые особенности: {features}. "
            f"Дизайн основан на принципах: {', '.join(style_data['keywords'][:3])}."
        )

    def _create_moodboard(self, style_data: dict, params: dict) -> dict:
        """Создать мудборд (текстовое представление)."""
        return {
            "colors": [
                {"name": c, "hex": self._color_to_hex(c)}
                for c in style_data["colors"]
            ],
            "materials": style_data["materials"],
            "textures": self._suggest_textures(style_data),
            "lighting": self._suggest_lighting(style_data),
            "references": style_data["keywords"],
        }

    def _extract_principles(self, style_data: dict, params: dict) -> list[str]:
        """Извлечь принципы дизайна."""
        principles = [
            f"Единство стиля: все элементы следуют принципам '{', '.join(style_data['keywords'][:2])}'",
            "Функциональность: каждое пространство имеет четкое назначение",
            "Гармония пропорций: соразмерность элементов",
        ]
        if "экологичный" in str(style_data.get("keywords", [])).lower():
            principles.append("Экологичность: использование натуральных материалов")
        return principles

    def _generate_recommendations(self, style_data: dict, params: dict) -> list[str]:
        recs = []
        for feature in style_data["features"][:3]:
            recs.append(f"Рекомендуется добавить: {feature}")
        for material in style_data["materials"][:2]:
            recs.append(f"Основной материал: {material}")
        return recs

    def _suggest_textures(self, style_data: dict) -> list[str]:
        textures = {
            "дерево": "Натуральное дерево (дуб, сосна)",
            "бетон": "Гладкий/фактурный бетон",
            "стекло": "Прозрачное/матовое стекло",
            "кирпич": "Красный/белый кирпич",
            "сталь": "Шлифованная сталь",
        }
        return [textures.get(m, m) for m in style_data["materials"][:3]]

    def _suggest_lighting(self, style_data: dict) -> list[str]:
        return ["Естественный свет через большие окна", "Точечное освещение", "Декоративная подсветка"]

    def _color_to_hex(self, color_name: str) -> str:
        """Название цвета → HEX код."""
        colors = {
            "белый": "#FFFFFF", "чёрный": "#1A1A1A", "серый": "#808080",
            "бежевый": "#F5F5DC", "коричневый": "#8B4513", "натуральное дерево": "#DEB887",
            "светлое дерево": "#F5DEB3", "кирпичный": "#CB4154", "терракотовый": "#E2725B",
            "зелёный": "#228B22", "голубой": "#87CEEB", "синий": "#4169E1",
            "серебристый": "#C0C0C0", "земляные тона": "#D2B48C",
        }
        return colors.get(color_name.lower(), "#808080")
