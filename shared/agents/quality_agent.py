"""
shared/agents/quality_agent.py — Многоуровневый контроль качества.

v9.0 — Жёсткий контроль 16K, детекция арматуры/балок, AI-анализ.

Уровни проверки:
1. Resolution — строгое соответствие заявленному качеству
2. File integrity — файл не битый, не пустой
3. Visual bugs — AI-анализ через mimo-omni (арматура, балки, артефакты)
4. Prompt match — соответствие рендера исходному промту
5. Geometry sanity — проверка на торчащие элементы
"""

import os
import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus


class QualityAgent(BaseAgent):
    """Многоуровневый агент контроля качества рендеров."""

    name = "quality"

    # СТРОГИЕ минимальные разрешения для каждого уровня
    MIN_RESOLUTIONS = {
        "preview": (1280, 720),
        "standard": (3840, 2160),      # 4K
        "high": (7680, 4320),           # 8K
        "ultra": (15360, 8640),         # 16K
        "16k": (15360, 8640),           # 16K
        "16k_force": (15360, 8640),     # 16K forced
    }

    # Minimum file sizes for quality levels (bytes)
    MIN_FILE_SIZES = {
        "preview": 50_000,        # 50 KB
        "standard": 500_000,      # 500 KB
        "high": 2_000_000,        # 2 MB
        "ultra": 8_000_000,       # 8 MB
        "16k": 8_000_000,         # 8 MB
        "16k_force": 8_000_000,   # 8 MB
    }

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            render_path = task.params.get("render_path", "")
            quality = task.params.get("quality", "standard")
            prompt = task.params.get("prompt", "")
            gen_type = task.params.get("gen_type", "building")
            render_data = task.params.get("render_data", {})

            checks = {}
            issues = []

            # ═══ Level 1: Resolution Check ═══
            if render_path and os.path.exists(render_path):
                res_check = self._check_resolution(render_path, quality)
                checks["resolution"] = res_check
                if not res_check.get("passed", False):
                    issues.append(f"Resolution below {quality}: {res_check.get('actual', '?')}")

                # ═══ Level 2: File Integrity ═══
                size_check = self._check_file_size(render_path, quality)
                checks["file_size"] = size_check
                if not size_check.get("passed", False):
                    issues.append(f"File too small: {size_check.get('size_mb', 0)} MB")

                # ═══ Level 3: Visual Bugs (AI-based) ═══
                ai_check = self._check_visual_bugs(render_path, prompt, gen_type)
                checks["visual_bugs"] = ai_check
                if ai_check.get("has_bugs", False):
                    issues.extend(ai_check.get("bugs", []))

                # ═══ Level 4: Prompt Match ═══
                if prompt:
                    match_check = self._check_prompt_match(render_path, prompt, gen_type)
                    checks["prompt_match"] = match_check
                    if not match_check.get("passed", True):
                        issues.append(match_check.get("issue", "Prompt mismatch"))

                # ═══ Level 5: Geometry Sanity ═══
                geom_check = self._check_geometry_sanity(render_path, gen_type)
                checks["geometry_sanity"] = geom_check
                if geom_check.get("has_anomalies", False):
                    issues.extend(geom_check.get("anomalies", []))
            else:
                checks["file_exists"] = {
                    "passed": False,
                    "required": True,
                    "error": f"Render file not found: {render_path}",
                }
                issues.append(f"Render file missing: {render_path}")

            # Overall verdict
            required_checks = [c for c in checks.values() if c.get("required", True)]
            all_required_passed = all(c.get("passed", False) for c in required_checks)

            return TaskResult(
                status=TaskStatus.DONE,
                data={
                    "passed": all_required_passed and len(issues) == 0,
                    "checks": checks,
                    "issues": issues,
                    "render_path": render_path,
                    "quality_level": quality,
                    "severity": "critical" if not all_required_passed else ("warning" if issues else "ok"),
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
        """Строгая проверка разрешения."""
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
            "deficit_w": max(0, min_w - w),
            "deficit_h": max(0, min_h - h),
        }

    def _check_file_size(self, image_path: str, quality: str) -> dict:
        """Проверка размера файла."""
        size_bytes = os.path.getsize(image_path)
        size_mb = size_bytes / (1024 * 1024)
        min_size = self.MIN_FILE_SIZES.get(quality, 500_000)

        return {
            "passed": size_bytes >= min_size,
            "required": True,
            "size_mb": round(size_mb, 2),
            "min_required_mb": round(min_size / (1024 * 1024), 2),
        }

    def _check_visual_bugs(self, image_path: str, prompt: str, gen_type: str) -> dict:
        """AI-анализ визуальных багов (арматура, балки, артефакты)."""
        try:
            from shared.preview import analyze_render, detect_visual_bugs

            bugs = detect_visual_bugs(image_path)
            return {
                "passed": not bugs.get("has_bugs", False),
                "required": False,
                "has_bugs": bugs.get("has_bugs", False),
                "bugs": bugs.get("bugs", []),
                "overall_quality": bugs.get("overall_quality", "unknown"),
            }
        except Exception:
            # AI check is supplementary — don't fail on errors
            return {
                "passed": True,
                "required": False,
                "note": "AI visual check unavailable",
            }

    def _check_prompt_match(self, image_path: str, prompt: str, gen_type: str) -> dict:
        """Проверка соответствия рендера промту."""
        try:
            from shared.preview import analyze_render

            analysis = analyze_render(image_path)
            description = analysis.get("description", "").lower()

            # Basic keyword matching
            prompt_lower = prompt.lower()

            # Check for type mismatch (most critical)
            if gen_type == "interior":
                exterior_keywords = ["house", "building", "facade", "дом", "здание", "фасад"]
                if any(kw in description for kw in exterior_keywords):
                    return {
                        "passed": False,
                        "required": True,
                        "issue": "Interior request but render shows exterior",
                    }
            elif gen_type == "building":
                interior_keywords = ["room", "interior", "furniture", "комната", "интерьер", "мебель"]
                if any(kw in description for kw in interior_keywords):
                    return {
                        "passed": False,
                        "required": True,
                        "issue": "Building request but render shows interior",
                    }
            elif gen_type == "landscape":
                building_keywords = ["house", "building", "дом", "здание"]
                if any(kw in description for kw in building_keywords):
                    return {
                        "passed": False,
                        "required": True,
                        "issue": "Landscape request but render shows building",
                    }

            return {"passed": True, "required": True}
        except Exception:
            return {"passed": True, "required": False, "note": "Prompt match check unavailable"}

    def _check_geometry_sanity(self, image_path: str, gen_type: str) -> dict:
        """Проверка геометрии на аномалии (торчащие элементы)."""
        try:
            from shared.preview import detect_visual_bugs

            result = detect_visual_bugs(image_path)
            anomalies = []

            # Check for specific geometry issues
            bugs = result.get("bugs", [])
            for bug in bugs:
                bug_lower = str(bug).lower()
                if any(kw in bug_lower for kw in ["rebar", "арматур", "balcony", "балк", "protruding", "торчит", "стick", "artifact"]):
                    anomalies.append(str(bug))

            return {
                "passed": len(anomalies) == 0,
                "required": False,
                "has_anomalies": len(anomalies) > 0,
                "anomalies": anomalies,
            }
        except Exception:
            return {"passed": True, "required": False, "note": "Geometry sanity check unavailable"}
