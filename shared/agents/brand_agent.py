"""
shared/agents/brand_agent.py — Агент бренд-стиля.

Отвечает за:
    - Определение фирменного архитектурного языка
    - Создание бренд-айдентики проекта
    - Генерацию названия и концепции бренда
    - Визуальный стиль (цвета, шрифты, материалы)
"""

import logging
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class BrandAgent(BaseAgent):
    name = "brand"

    # Стили → визуальный язык
    VISUAL_LANGUAGES = {
        "luxury": {
            "colors": ["#C9B037", "#1A1A1A", "#F5F5DC", "#8B4513"],
            "fonts": ["Didot", "Bodoni", "Playfair Display"],
            "materials": ["мрамор", "натуральный камень", "золото", "тёмное дерево"],
            "mood": "Элегантность, роскошь, статус",
            "keywords": ["exclusive", "premium", "bespoke", "artisan"],
        },
        "modern": {
            "colors": ["#FFFFFF", "#333333", "#E74C3C", "#3498DB"],
            "fonts": ["Helvetica Neue", "Roboto", "Inter"],
            "materials": ["стекло", "сталь", "бетон", "дерево"],
            "mood": "Чистота, инновации, технологии",
            "keywords": ["innovative", "smart", "sustainable", "minimal"],
        },
        "eco": {
            "colors": ["#27AE60", "#8B4513", "#F5DEB3", "#87CEEB"],
            "fonts": ["Source Sans Pro", "Open Sans", "Lato"],
            "materials": ["дерево", "камень", "глина", "солома"],
            "mood": "Природа, гармония, устойчивость",
            "keywords": ["green", "sustainable", "natural", "organic"],
        },
        "industrial": {
            "colors": ["#2C3E50", "#95A5A6", "#E74C3C", "#F39C12"],
            "fonts": ["Montserrat", "Oswald", "Bebas Neue"],
            "materials": ["кирпич", "бетон", "сталь", "стекло"],
            "mood": "Сила, характер, авангард",
            "keywords": ["raw", "bold", "urban", "authentic"],
        },
        "classic": {
            "colors": ["#F5F5DC", "#8B4513", "#DEB887", "#2F4F4F"],
            "fonts": ["Georgia", "Garamond", "Times New Roman"],
            "materials": ["камень", "штукатурка", "дерево", "черепица"],
            "mood": "Традиция, надёжность, преемственность",
            "keywords": ["heritage", "timeless", "elegant", "refined"],
        },
    }

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            brand = self._create_brand(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=brand,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"BrandAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _create_brand(self, params: dict) -> dict:
        """Создать бренд-айдентику."""
        style = params.get("style", "modern").lower()
        building_type = params.get("building_type", "house")
        name_hint = params.get("name", "")

        # Определяем визуальный язык
        lang = self.VISUAL_LANGUAGES.get(style, self.VISUAL_LANGUAGES["modern"])

        # Генерация названия
        brand_name = name_hint or self._generate_name(style, building_type)

        # Логотип (текстовое описание)
        logo_desc = self._describe_logo(brand_name, lang)

        # Фирменный стиль
        identity = {
            "type": "brand",
            "brand_name": brand_name,
            "style": style,
            "mood": lang["mood"],
            "visual_language": {
                "primary_colors": lang["colors"],
                "fonts": lang["fonts"],
                "materials": lang["materials"],
                "keywords": lang["keywords"],
            },
            "logo_description": logo_desc,
            "brand_guidelines": self._create_guidelines(brand_name, lang, params),
            "tagline": self._generate_tagline(brand_name, style, building_type),
            "application": {
                "facade": self._brand_to_facade(lang, params),
                "interior": self._brand_to_interior(lang, params),
                "signage": self._brand_to_signage(brand_name, lang),
                "marketing": self._brand_to_marketing(brand_name, lang),
            },
        }

        return identity

    def _generate_name(self, style: str, building_type: str) -> str:
        """Генерация названия проекта."""
        prefixes = {
            "luxury": ["Aurelia", "Prestige", "Imperial", "Grand"],
            "modern": ["Nexus", "Vertex", "Pulse", "Nova"],
            "eco": ["Green Haven", "Eco Nest", "Bio Home", "Nature's Edge"],
            "industrial": ["Forge", "Loft Hub", "Iron Gate", "Urban Core"],
            "classic": ["Heritage", "Estate", "Manor", "Villa"],
        }
        suffixes = {
            "house": ["Residence", "Home", "House"],
            "cottage": ["Cottage", "Retreat", "Lodge"],
            "villa": ["Villa", "Estate", "Manor"],
            "office": ["Tower", "Center", "Hub"],
        }

        prefix_list = prefixes.get(style, prefixes["modern"])
        suffix_list = suffixes.get(building_type, suffixes["house"])

        import random

        return f"{random.choice(prefix_list)} {random.choice(suffix_list)}"

    def _describe_logo(self, name: str, lang: dict) -> str:
        """Описание логотипа."""
        return (
            f"Логотип '{name}': минималистичный, использует "
            f"{lang['fonts'][0]}, цвета: {', '.join(lang['colors'][:2])}. "
            f"Геометрический символ, отражающий архитектурную тематику."
        )

    def _create_guidelines(self, name: str, lang: dict, params: dict) -> dict:
        """Гайдлайн бренд-стиля."""
        return {
            "logo_clear_space": "Минимум 2x высоты логотипа",
            "minimum_size": "24px (цифровой), 10мм (печать)",
            "color_usage": {
                "primary": lang["colors"][0],
                "secondary": lang["colors"][1] if len(lang["colors"]) > 1 else "#333333",
                "accent": lang["colors"][2] if len(lang["colors"]) > 2 else "#E74C3C",
            },
            "typography": {
                "heading": lang["fonts"][0],
                "body": lang["fonts"][1] if len(lang["fonts"]) > 1 else "sans-serif",
            },
            "do": [
                "Использовать логотип на чистом фоне",
                "Соблюдать минимальные отступы",
                "Использовать фирменные цвета",
            ],
            "dont": [
                "Не искажать пропорции логотипа",
                "Не использовать на пёстром фоне",
                "Не менять цвета логотипа",
            ],
        }

    def _generate_tagline(self, name: str, style: str, building_type: str) -> str:
        """Генерация слогана."""
        taglines = {
            "luxury": f"{name} — искусство жить",
            "modern": f"{name} — будущее начинается здесь",
            "eco": f"{name} — в гармонии с природой",
            "industrial": f"{name} — характер в каждой детали",
            "classic": f"{name} — проверено временем",
        }
        return taglines.get(style, f"{name} — ваш идеальный дом")

    def _brand_to_facade(self, lang: dict, params: dict) -> dict:
        """Применение бренда к фасаду."""
        return {
            "main_material": lang["materials"][0],
            "accent_material": lang["materials"][1] if len(lang["materials"]) > 1 else "стекло",
            "color_scheme": lang["colors"][:3],
            "features": [
                "Фирменная табличка с названием",
                "Подсветка входной группы",
                "Ландшафтный дизайн в стиле бренда",
            ],
        }

    def _brand_to_interior(self, lang: dict, params: dict) -> dict:
        """Применение бренда к интерьеру."""
        return {
            "palette": lang["colors"],
            "materials": lang["materials"],
            "furniture_style": lang["mood"],
            "accent_elements": [
                "Фирменные акценты в отделке",
                "Мебель в стиле бренда",
                "Освещение подчёркивает характер",
            ],
        }

    def _brand_to_signage(self, name: str, lang: dict) -> dict:
        """Вывески и навигация."""
        return {
            "main_sign": f"Объёмные буквы '{name}'",
            "material": lang["materials"][0],
            "illumination": "Контражурная подсветка",
            "navigation": "Минималистичные указатели",
        }

    def _brand_to_marketing(self, name: str, lang: dict) -> dict:
        """Маркетинговые материалы."""
        return {
            "business_cards": "Визитки на плотной бумаге, тиснение",
            "presentation": "Презентация в фирменных цветах",
            "website": f"Лендинг в стиле {lang['mood']}",
            "social_media": "Шаблоны для Instagram/VK",
        }
