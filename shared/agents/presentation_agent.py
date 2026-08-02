"""
shared/agents/presentation_agent.py — Агент генерации презентаций.

Отвечает за:
    - Создание презентаций проекта
    - Генерацию слайдов с рендерами, планами, описаниями
    - Подготовку маркетинговых материалов
    - Экспорт в PDF/HTML/PPTX
"""

import logging
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class PresentationAgent(BaseAgent):
    name = "presentation"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            presentation = self._generate_presentation(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=presentation,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error(f"PresentationAgent error: {e}")
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _generate_presentation(self, params: dict) -> dict:
        """Генерация презентации проекта."""
        project_name = params.get("project_name", "Архитектурный проект")
        style = params.get("style", "modern")
        building_type = params.get("building_type", "house")
        render_paths = params.get("render_paths", [])
        floor_plan_path = params.get("floor_plan_path", "")
        concept = params.get("concept", {})
        cost_estimate = params.get("cost_estimate", {})
        norm_report = params.get("norm_report", {})
        masterplan = params.get("masterplan", {})

        slides = []

        # Слайд 1: Титульный
        slides.append(self._title_slide(project_name, style, building_type))

        # Слайд 2: Концепция
        if concept:
            slides.append(self._concept_slide(concept))

        # Слайд 3: Рендеры
        if render_paths:
            slides.append(self._renders_slide(render_paths))

        # Слайд 4: План участка
        if masterplan:
            slides.append(self._masterplan_slide(masterplan))

        # Слайд 5: План этажа
        if floor_plan_path:
            slides.append(self._floorplan_slide(floor_plan_path))

        # Слайд 6: Технические характеристики
        slides.append(self._specs_slide(params))

        # Слайд 7: Смета
        if cost_estimate:
            slides.append(self._cost_slide(cost_estimate))

        # Слайд 8: Соответствие нормам
        if norm_report:
            slides.append(self._compliance_slide(norm_report))

        # Слайд 9: Ландшафт
        if params.get("landscape"):
            slides.append(self._landscape_slide(params["landscape"]))

        # Слайд 10: Контакты / Следующие шаги
        slides.append(self._closing_slide(project_name))

        # Генерация HTML презентации
        html = self._to_html(slides, project_name, style)

        return {
            "type": "presentation",
            "project_name": project_name,
            "slides_count": len(slides),
            "slides": slides,
            "html": html,
            "formats": ["html", "pdf"],
        }

    def _title_slide(self, name: str, style: str, building_type: str) -> dict:
        return {
            "type": "title",
            "title": name,
            "subtitle": f"{style.title()} {building_type}",
            "background": "gradient",
            "elements": ["logo", "date", "project_number"],
        }

    def _concept_slide(self, concept: dict) -> dict:
        return {
            "type": "concept",
            "title": "Концепция проекта",
            "description": concept.get("description", ""),
            "keywords": concept.get("keywords", []),
            "color_palette": concept.get("color_palette", []),
            "material_palette": concept.get("material_palette", []),
        }

    def _renders_slide(self, render_paths: list) -> dict:
        return {
            "type": "renders",
            "title": "Визуализация",
            "images": render_paths,
            "layout": "gallery" if len(render_paths) > 2 else "single",
        }

    def _masterplan_slide(self, masterplan: dict) -> dict:
        return {
            "type": "masterplan",
            "title": "Генеральный план",
            "lot_area": masterplan.get("lot", {}).get("area_m2", 0),
            "building_coverage": masterplan.get("area_calculation", {}).get("building_coverage", 0),
            "green_coverage": masterplan.get("area_calculation", {}).get("green_coverage", 0),
            "zones": [z.get("label", z["name"]) for z in masterplan.get("zones", [])],
        }

    def _floorplan_slide(self, plan_path: str) -> dict:
        return {
            "type": "floorplan",
            "title": "План этажа",
            "image": plan_path,
        }

    def _specs_slide(self, params: dict) -> dict:
        return {
            "type": "specs",
            "title": "Технические характеристики",
            "specs": {
                "Тип": params.get("building_type", "—"),
                "Этажность": params.get("floors", "—"),
                "Размеры": f"{params.get('width_m', '—')}×{params.get('length_m', '—')} м",
                "Высота": f"{params.get('height_m', '—')} м",
                "Материал": params.get("material", "—"),
                "Кровля": params.get("roof_type", "—"),
                "Площадь": f"{params.get('width_m', 10) * params.get('length_m', 10) * params.get('floors', 1)} м²",
            },
        }

    def _cost_slide(self, cost: dict) -> dict:
        return {
            "type": "cost",
            "title": "Смета",
            "total": cost.get("total", 0),
            "breakdown": cost.get("breakdown", {}),
            "cost_per_m2": cost.get("cost_per_m2", 0),
            "currency": "₽",
        }

    def _compliance_slide(self, norm_report: dict) -> dict:
        return {
            "type": "compliance",
            "title": "Соответствие нормам",
            "passed": norm_report.get("passed", False),
            "score": norm_report.get("score", 0),
            "summary": norm_report.get("summary", ""),
            "violations_count": norm_report.get("violations", 0),
        }

    def _landscape_slide(self, landscape: dict) -> dict:
        return {
            "type": "landscape",
            "title": "Ландшафтный дизайн",
            "style": landscape.get("style", ""),
            "plant_count": landscape.get("plant_count", {}),
            "zones": [z.get("label", z["name"]) for z in landscape.get("zones", [])],
        }

    def _closing_slide(self, name: str) -> dict:
        return {
            "type": "closing",
            "title": "Спасибо за внимание",
            "subtitle": name,
            "elements": ["contact_info", "qr_code", "social_links"],
            "call_to_action": "Свяжитесь с нами для обсуждения проекта",
        }

    def _to_html(self, slides: list, project_name: str, style: str) -> str:
        """Генерация HTML презентации."""
        color_schemes = {
            "modern": {"bg": "#1a1a2e", "text": "#eee", "accent": "#e94560"},
            "classic": {"bg": "#f5f0e8", "text": "#2c2c2c", "accent": "#8b4513"},
            "eco": {"bg": "#f0f7f0", "text": "#2c3e2c", "accent": "#27ae60"},
            "luxury": {"bg": "#1a1a1a", "text": "#f5f5dc", "accent": "#c9b037"},
        }
        colors = color_schemes.get(style, color_schemes["modern"])

        html_parts = [
            "<!DOCTYPE html>",
            '<html lang="ru">',
            "<head>",
            f"<title>{project_name}</title>",
            '<meta charset="UTF-8">',
            "<style>",
            f'body {{ background: {colors["bg"]}; color: {colors["text"]}; font-family: "Helvetica Neue", sans-serif; margin: 0; }}',
            ".slide { min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 60px; box-sizing: border-box; page-break-after: always; }",
            f".accent {{ color: {colors['accent']}; }}",
            "h1 { font-size: 3em; margin-bottom: 0.3em; }",
            "h2 { font-size: 2em; margin-bottom: 0.5em; }",
            ".specs-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; max-width: 600px; }",
            ".spec-item { background: rgba(255,255,255,0.1); padding: 15px; border-radius: 8px; }",
            ".cost-breakdown { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; text-align: center; }",
            ".cost-item { padding: 20px; }",
            ".cost-value { font-size: 2em; font-weight: bold; }",
            "</style>",
            "</head>",
            "<body>",
        ]

        for i, slide in enumerate(slides):
            html_parts.append(f'<div class="slide" id="slide-{i + 1}">')

            if slide["type"] == "title":
                html_parts.append(f"<h1>{slide['title']}</h1>")
                html_parts.append(f'<p class="accent">{slide["subtitle"]}</p>')

            elif slide["type"] == "concept":
                html_parts.append(f"<h2>{slide['title']}</h2>")
                html_parts.append(f"<p>{slide.get('description', '')}</p>")
                if slide.get("keywords"):
                    html_parts.append(f'<p class="accent">{" · ".join(slide["keywords"])}</p>')

            elif slide["type"] == "specs":
                html_parts.append(f"<h2>{slide['title']}</h2>")
                html_parts.append('<div class="specs-grid">')
                for key, val in slide.get("specs", {}).items():
                    html_parts.append(f'<div class="spec-item"><strong>{key}</strong><br>{val}</div>')
                html_parts.append("</div>")

            elif slide["type"] == "cost":
                html_parts.append(f"<h2>{slide['title']}</h2>")
                html_parts.append(f'<p class="cost-value accent">{slide.get("total", 0):,} ₽</p>')
                html_parts.append(f"<p>{slide.get('cost_per_m2', 0):,} ₽/м²</p>")

            elif slide["type"] == "compliance":
                status = "✅ Соответствует" if slide.get("passed") else "⚠️ Есть замечания"
                html_parts.append(f"<h2>{slide['title']}</h2>")
                html_parts.append(f'<p class="accent">{status}</p>')
                html_parts.append(f"<p>{slide.get('summary', '')}</p>")

            elif slide["type"] == "closing":
                html_parts.append(f"<h1>{slide['title']}</h1>")
                html_parts.append(f"<p>{slide.get('call_to_action', '')}</p>")

            else:
                html_parts.append(f"<h2>{slide.get('title', slide['type'])}</h2>")

            html_parts.append("</div>")

        html_parts.extend(["</body>", "</html>"])
        return "\n".join(html_parts)
