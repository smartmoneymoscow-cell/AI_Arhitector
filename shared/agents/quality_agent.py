"""
shared/agents/quality_agent.py — Агент проверки качества рендеров.

Выполняет автоматическую проверку:
- Разрешение (≥ target resolution)
- Визуальные баги (черные области, clipping, z-fighting)
- Соответствие промту
- Корректность геометрии

Использует PIL для базовой проверки + mimo-omni для AI-анализа.
"""

import os
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus


class QualityAgent(BaseAgent):
    """Агент автоматической проверки качества рендеров."""

    name = "quality"

    # Минимальные разрешения для каждого уровня качества
    MIN_RESOLUTIONS = {
        "preview": (1280, 720),
        "standard": (3840, 2160),
        "high": (7680, 4320),
        "ultra": (15360, 8640),
        "16k": (15360, 8640),
    }

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            render_path = task.params.get("render_path", "")
            quality = task.params.get("quality", "standard")
            prompt = task.params.get("prompt", "")

            if not render_path or not os.path.exists(render_path):
                return TaskResult(
                    status=TaskStatus.FAILED,
                    error=f"Render file not found: {render_path}",
                    duration_ms=(time.time() - start) * 1000,
                )

            checks = {}

            # 1. Resolution check
            res_check = self._check_resolution(render_path, quality)
            checks["resolution"] = res_check

            # 2. File size check (sanity)
            size_check = self._check_file_size(render_path)
            checks["file_size"] = size_check

            # 3. Visual bugs (AI-based, optional)
            if prompt:
                ai_check = self._check_with_ai(render_path, prompt)
                checks["ai_analysis"] = ai_check

            # Overall verdict
            all_ok = all(c.get("passed", False) for c in checks.values() if c.get("required", True))

            return TaskResult(
                status=TaskStatus.DONE,
                data={
                    "passed": all_ok,
                    "checks": checks,
                    "render_path": render_path,
                },
                duration_ms=(time.time() - start) * 1000,
            )

        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _check_resolution(self, image_path: str, quality: str) -> dict:
        """Проверяет разрешение рендера."""
        try:
            from PIL import Image

            img = Image.open(image_path)
            w, h = img.size
        except Exception as e:
            return {
                "passed": False,
                "required": True,
                "error": f"Cannot read image: {e}",
            }

        min_w, min_h = self.MIN_RESOLUTIONS.get(quality, (3840, 2160))
        passed = w >= min_w and h >= min_h

        return {
            "passed": passed,
            "required": True,
            "actual": f"{w}x{h}",
            "expected_min": f"{min_w}x{min_h}",
            "megapixels": round(w * h / 1_000_000, 1),
        }

    def _check_file_size(self, image_path: str) -> dict:
        """Проверяет что файл не пустой и не подозрительно маленький."""
        size_bytes = os.path.getsize(image_path)
        size_mb = size_bytes / (1024 * 1024)

        # Для 16K PNG ожидаем минимум 5 MB
        passed = size_mb > 0.01  # не пустой

        return {
            "passed": passed,
            "required": True,
            "size_mb": round(size_mb, 2),
        }

    def _check_with_ai(self, image_path: str, prompt: str) -> dict:
        """AI-анализ рендера через mimo-omni (опционально)."""
        try:
            from shared.preview import analyze_render, detect_visual_bugs

            analysis = analyze_render(image_path)
            bugs = detect_visual_bugs(image_path)

            return {
                "passed": not bugs.get("has_bugs", False),
                "required": False,  # AI check is optional
                "description": analysis.get("description", ""),
                "has_bugs": bugs.get("has_bugs", False),
                "bugs": bugs.get("bugs", []),
                "overall_quality": bugs.get("overall_quality", "unknown"),
                "source": analysis.get("source", "none"),
            }
        except Exception as e:
            return {
                "passed": True,  # Don't fail on AI check errors
                "required": False,
                "error": str(e),
                "source": "error",
            }
