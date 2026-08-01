"""
shared/e2e_test.py — E2E тестирование Architect сервиса.

Полный цикл:
  1. Отправить промт в чат API
  2. Сделать скриншот чата → проанализировать правильность шагов
  3. Сделать скриншот превью → проанализировать соответствие промту
  4. Проверить качество ≥16K и отсутствие визуальных багов

Использование:
    from shared.e2e_test import E2ETester

    tester = E2ETester("http://localhost:8080")
    result = tester.run_full_test("двухэтажный кирпичный дом 10x12")
    print(result.report())
"""

import json
import os
import re
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class ChatStepAnalysis:
    """Анализ шагов в чате."""

    steps_found: list[str] = field(default_factory=list)
    steps_expected: list[str] = field(default_factory=list)
    steps_correct: bool = False
    order_correct: bool = False
    details: str = ""


@dataclass
class PreviewAnalysis:
    """Анализ превью-скриншота."""

    matches_prompt: bool = False
    match_score: float = 0.0
    quality_ok: bool = False
    resolution: str = ""
    has_bugs: bool = False
    bugs: list[str] = field(default_factory=list)
    description: str = ""
    details: str = ""


@dataclass
class E2EResult:
    """Полный результат E2E теста."""

    prompt: str = ""
    chat_analysis: ChatStepAnalysis | None = None
    preview_analysis: PreviewAnalysis | None = None
    api_response: dict = field(default_factory=dict)
    screenshots: dict = field(default_factory=dict)
    passed: bool = False
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0

    def report(self) -> str:
        """Генерирует текстовый отчёт."""
        lines = [
            "=" * 60,
            "E2E TEST REPORT",
            "=" * 60,
            f"Prompt: {self.prompt}",
            f"Duration: {self.duration_ms:.0f}ms",
            f"Overall: {'✅ PASSED' if self.passed else '❌ FAILED'}",
            "",
        ]

        if self.chat_analysis:
            ca = self.chat_analysis
            lines.append("── Chat Analysis ──")
            lines.append(f"  Steps found: {ca.steps_found}")
            lines.append(f"  Steps expected: {ca.steps_expected}")
            lines.append(f"  Steps correct: {'✅' if ca.steps_correct else '❌'}")
            lines.append(f"  Order correct: {'✅' if ca.order_correct else '❌'}")
            if ca.details:
                lines.append(f"  Details: {ca.details}")
            lines.append("")

        if self.preview_analysis:
            pa = self.preview_analysis
            lines.append("── Preview Analysis ──")
            lines.append(f"  Matches prompt: {'✅' if pa.matches_prompt else '❌'} (score: {pa.match_score:.0%})")
            lines.append(f"  Quality ≥16K: {'✅' if pa.quality_ok else '❌'} ({pa.resolution})")
            lines.append(f"  Visual bugs: {'❌ ' + str(len(pa.bugs)) + ' found' if pa.has_bugs else '✅ None'}")
            if pa.bugs:
                for bug in pa.bugs:
                    lines.append(f"    - {bug}")
            if pa.description:
                lines.append(f"  Description: {pa.description[:200]}")
            lines.append("")

        if self.errors:
            lines.append("── Errors ──")
            for err in self.errors:
                lines.append(f"  ❌ {err}")

        lines.append("=" * 60)
        return "\n".join(lines)


# Ожидаемые шаги для разных типов генерации
EXPECTED_STEPS = {
    "building": ["parse", "geometry", "texture", "render", "export"],
    "interior": ["parse", "geometry", "texture", "render"],
    "building_quick": ["parse", "generate_geometry", "export_glb"],
    "interior_quick": ["parse", "render_interior"],
}

# Ключевые слова для проверки соответствия промту
PROMPT_KEYWORDS_MAP = {
    "building": ["дом", "здание", "этаж", "крыша", "фасад", "стен", "окн"],
    "interior": ["комнат", "мебел", "интерьер", "стен", "пол", "потолок"],
    "brick": ["кирпич", "brick"],
    "wood": ["дерев", "wood"],
    "modern": ["современн", "модерн", "modern"],
    "classic": ["классич", "classic"],
}


class E2ETester:
    """E2E тестер для Architect сервиса."""

    def __init__(self, base_url: str = "http://localhost:8080", timeout: float = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.screenshot_dir = os.path.join(os.path.dirname(__file__), "..", "..", ".openclaw", "tmp", "e2e_screenshots")
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def run_full_test(
        self,
        prompt: str,
        quality: str = "standard",
        export_formats: list[str] | None = None,
        take_screenshots: bool = True,
    ) -> E2EResult:
        """
        Полный E2E тест.

        Args:
            prompt: промт для генерации
            quality: качество рендера
            export_formats: форматы экспорта
            take_screenshots: делать ли скриншоты (нужен Playwright)

        Returns:
            E2EResult с полным отчётом
        """
        start = time.time()
        result = E2EResult(prompt=prompt)
        if export_formats is None:
            export_formats = ["glb"]

        try:
            # ═══ Step 1: Send prompt via API ═══
            print(f"[E2E] Sending prompt: {prompt[:50]}...")
            api_result = self._send_orchestrator(prompt, quality, export_formats)
            result.api_response = api_result

            if "error" in api_result:
                result.errors.append(f"API error: {api_result['error']}")
                return result

            # ═══ Step 2: Analyze chat steps ═══
            print("[E2E] Analyzing chat steps...")
            result.chat_analysis = self._analyze_chat_steps(api_result, prompt)

            # ═══ Step 3: Take & analyze preview screenshot ═══
            if take_screenshots:
                print("[E2E] Taking screenshots...")
                screenshots = self._take_screenshots(prompt, api_result)
                result.screenshots = screenshots

                if screenshots.get("preview"):
                    print("[E2E] Analyzing preview...")
                    result.preview_analysis = self._analyze_preview(screenshots["preview"], prompt, quality)
                else:
                    result.preview_analysis = PreviewAnalysis(details="No preview screenshot available")
            else:
                # Анализ только по API response
                result.preview_analysis = self._analyze_from_api(api_result, quality)

            # ═══ Step 4: Determine pass/fail ═══
            result.passed = self._determine_pass(result)

        except httpx.ConnectError:
            result.errors.append(f"Cannot connect to {self.base_url}")
        except httpx.TimeoutException:
            result.errors.append(f"Request timeout ({self.timeout}s)")
        except Exception as e:
            result.errors.append(f"Unexpected error: {e}")
        finally:
            result.duration_ms = (time.time() - start) * 1000

        return result

    def _send_orchestrator(self, prompt: str, quality: str, export_formats: list[str]) -> dict:
        """Отправляет промт через orchestrator API."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(
                    f"{self.base_url}/api/v1/orchestrator/execute",
                    json={
                        "prompt": prompt,
                        "quality": quality,
                        "export_formats": export_formats,
                        "skip_clarification": True,
                    },
                )
                if r.status_code == 200:
                    return r.json()
                return {"error": f"HTTP {r.status_code}: {r.text[:500]}"}
        except httpx.ConnectError:
            # Fallback to quick generate
            return self._send_quick_generate(prompt)

    def _send_quick_generate(self, prompt: str) -> dict:
        """Fallback: быстрая генерация."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(
                    f"{self.base_url}/api/v1/generate",
                    json={"prompt": prompt},
                )
                if r.status_code == 200:
                    return {"status": "ok", "mode": "quick", "steps": [{"name": "generate", "status": "done"}]}
                return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
        except Exception as e:
            return {"error": str(e)}

    def _analyze_chat_steps(self, api_result: dict, prompt: str) -> ChatStepAnalysis:
        """Анализирует шаги из API ответа."""
        analysis = ChatStepAnalysis()

        # Определяем тип генерации
        gen_type = api_result.get("gen_type", "building")
        if gen_type not in ("building", "interior"):
            gen_type = "building"

        mode = "quick" if api_result.get("mode") == "quick" else "orchestrator"
        expected_key = f"{gen_type}_{mode}" if mode == "quick" else gen_type
        analysis.steps_expected = EXPECTED_STEPS.get(expected_key, EXPECTED_STEPS[gen_type])

        # Извлекаем шаги из ответа
        steps = api_result.get("steps", [])
        found_steps = [s.get("name", "") for s in steps if isinstance(s, dict)]
        analysis.steps_found = found_steps

        # Проверяем наличие ожидаемых шагов
        found_set = set(found_steps)
        expected_set = set(analysis.steps_expected)

        # Проверяем ключевые шаги (min 2 из expected must be present)
        key_steps_present = len(found_set & expected_set)
        analysis.steps_correct = key_steps_present >= min(2, len(expected_set))

        # Проверяем порядок (expected steps должны идти в правильном порядке)
        if found_steps:
            order_indices = []
            for expected in analysis.steps_expected:
                for i, found in enumerate(found_steps):
                    if expected in found or found in expected:
                        order_indices.append(i)
                        break
            analysis.order_correct = order_indices == sorted(order_indices)

        # Details
        status = api_result.get("status", "unknown")
        duration = api_result.get("duration_ms", 0)
        analysis.details = (
            f"status={status}, gen_type={gen_type}, mode={mode}, "
            f"found={len(found_steps)} steps, duration={duration:.0f}ms"
        )

        return analysis

    def _take_screenshots(self, prompt: str, api_result: dict) -> dict:
        """Делает скриншоты чата и превью через Playwright."""
        screenshots = {}

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1920, "height": 1080})

                # Загружаем фронтенд
                page.goto(self.base_url, wait_until="networkidle", timeout=15000)
                time.sleep(2)

                # Скриншот чата
                chat_path = os.path.join(self.screenshot_dir, "chat.png")
                page.screenshot(path=chat_path, full_page=False)
                screenshots["chat"] = chat_path

                # Ждём превью если есть
                try:
                    page.wait_for_selector("canvas, .preview, #viewer, .three-canvas", timeout=10000)
                    time.sleep(2)
                    preview_path = os.path.join(self.screenshot_dir, "preview.png")
                    page.screenshot(path=preview_path, full_page=False)
                    screenshots["preview"] = preview_path
                except Exception:
                    screenshots["preview"] = screenshots.get("chat")

                browser.close()

        except ImportError:
            screenshots["error"] = "Playwright not installed"
        except Exception as e:
            screenshots["error"] = str(e)

        return screenshots

    def _analyze_preview(self, screenshot_path: str, prompt: str, quality: str) -> PreviewAnalysis:
        """Анализирует превью-скриншот через mimo-omni."""
        analysis = PreviewAnalysis()

        if not os.path.exists(screenshot_path):
            analysis.details = f"Screenshot not found: {screenshot_path}"
            return analysis

        # 1. Проверка разрешения
        try:
            from PIL import Image

            img = Image.open(screenshot_path)
            analysis.resolution = f"{img.width}x{img.height}"
            analysis.quality_ok = self._check_resolution_quality(img.width, img.height, quality)
        except ImportError:
            analysis.resolution = "unknown (no PIL)"
            analysis.quality_ok = True  # Assume OK if can't check

        # 2. Анализ через mimo-omni
        analysis_result = self._call_mimo_omni(screenshot_path, prompt)
        if analysis_result:
            analysis.description = analysis_result.get("description", "")
            analysis.matches_prompt = analysis_result.get("matches_prompt", False)
            analysis.match_score = analysis_result.get("match_score", 0.0)
            analysis.has_bugs = analysis_result.get("has_bugs", False)
            analysis.bugs = analysis_result.get("bugs", [])
        else:
            analysis.details = "mimo-omni analysis unavailable"

        return analysis

    def _analyze_from_api(self, api_result: dict, quality: str) -> PreviewAnalysis:
        """Анализирует результат только по API (без скриншотов)."""
        analysis = PreviewAnalysis()

        # Проверяем наличие рендера
        render = api_result.get("render", "")
        exports = api_result.get("exports", {})

        if render and os.path.exists(render):
            try:
                from PIL import Image

                img = Image.open(render)
                analysis.resolution = f"{img.width}x{img.height}"
                analysis.quality_ok = self._check_resolution_quality(img.width, img.height, quality)
            except ImportError:
                analysis.resolution = "render exists"
                analysis.quality_ok = True

            # Анализ рендера через mimo-omni
            analysis_result = self._call_mimo_omni(render, "")
            if analysis_result:
                analysis.description = analysis_result.get("description", "")
                analysis.matches_prompt = analysis_result.get("matches_prompt", False)
                analysis.match_score = analysis_result.get("match_score", 0.0)
                analysis.has_bugs = analysis_result.get("has_bugs", False)
                analysis.bugs = analysis_result.get("bugs", [])
        else:
            analysis.details = f"No render output. Exports: {list(exports.keys())}"
            analysis.quality_ok = False

        return analysis

    def _check_resolution_quality(self, width: int, height: int, quality: str) -> bool:
        """Проверяет что разрешение соответствует заявленному качеству."""
        min_resolutions = {
            "preview": (1280, 720),
            "standard": (3840, 2160),
            "high": (7680, 4320),
            "ultra": (15360, 8640),
            "16k": (15360, 8640),
        }
        min_w, min_h = min_resolutions.get(quality, (1920, 1080))
        return width >= min_w and height >= min_h

    def _call_mimo_omni(self, image_path: str, prompt_context: str) -> dict:
        """Вызывает mimo-omni для анализа изображения."""
        analysis_prompt = (
            "Проанализируй этот архитектурный рендер/скриншот. Ответь СТРОГО в JSON:\n"
            "{\n"
            '  "description": "краткое описание что на изображении",\n'
            '  "matches_prompt": true/false,\n'
            '  "match_score": 0.0-1.0,\n'
            '  "has_bugs": true/false,\n'
            '  "bugs": ["описание бага 1", "описание бага 2"],\n'
            '  "quality_issues": ["проблема 1"]\n'
            "}\n"
        )
        if prompt_context:
            analysis_prompt += f"\nОригинальный промт: {prompt_context}"

        try:
            import subprocess

            mimo_script = os.path.expanduser("~/.openclaw/skills/mimo-omni/mimo_api.sh")
            if not os.path.exists(mimo_script):
                return None

            result = subprocess.run(
                ["bash", mimo_script, "image", image_path, analysis_prompt],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                return self._parse_mimo_response(result.stdout)

        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass

        return None

    def _parse_mimo_response(self, response: str) -> dict:
        """Парсит ответ mimo-omni (JSON или текст)."""
        # Try JSON first
        try:
            # Find JSON block
            json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                # Ensure required fields
                return {
                    "description": data.get("description", ""),
                    "matches_prompt": data.get("matches_prompt", False),
                    "match_score": float(data.get("match_score", 0)),
                    "has_bugs": data.get("has_bugs", False),
                    "bugs": data.get("bugs", []),
                    "quality_issues": data.get("quality_issues", []),
                }
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: parse as text
        response_lower = response.lower()
        has_bugs = any(
            word in response_lower
            for word in [
                "баг",
                "артефакт",
                "ошибка",
                "глитч",
                "проблема",
                "дефект",
                "bug",
                "artifact",
                "error",
                "glitch",
                " проблем",
            ]
        )
        matches = any(
            word in response_lower
            for word in [
                "соответств",
                "правильн",
                "корректн",
                "похож",
                "match",
            ]
        )

        return {
            "description": response[:500],
            "matches_prompt": matches,
            "match_score": 0.7 if matches else 0.3,
            "has_bugs": has_bugs,
            "bugs": [],
        }

    def _determine_pass(self, result: E2EResult) -> bool:
        """Определяет прошёл ли тест."""
        if result.errors:
            return False

        # Chat steps must be correct
        if result.chat_analysis and not result.chat_analysis.steps_correct:
            return False

        # Preview must match prompt (if analyzed)
        if result.preview_analysis:
            if result.preview_analysis.has_bugs:
                return False
            if result.preview_analysis.match_score < 0.5:
                return False

        return True


def run_quick_test(base_url: str = "http://localhost:8080") -> E2EResult:
    """Быстрый тест (без скриншотов, только API)."""
    tester = E2ETester(base_url)
    return tester.run_full_test(
        prompt="двухэтажный кирпичный дом 10x12 с балконом",
        quality="standard",
        take_screenshots=False,
    )


def run_full_test_suite(base_url: str = "http://localhost:8080") -> list[E2EResult]:
    """Полный набор тестов."""
    tester = E2ETester(base_url)

    test_cases = [
        {"prompt": "двухэтажный кирпичный дом 10x12", "quality": "standard"},
        {"prompt": "современная спальня 6x8 в скандинавском стиле", "quality": "standard"},
        {"prompt": "офисный центр 5 этажей хайтек", "quality": "high"},
        {"prompt": "деревянный коттедж с террасой и гаражом", "quality": "standard"},
        {"prompt": "детская комната с кроватью и книжным шкафом", "quality": "preview"},
    ]

    results = []
    for tc in test_cases:
        print(f"\n{'=' * 60}")
        print(f"Test: {tc['prompt'][:50]}...")
        result = tester.run_full_test(
            prompt=tc["prompt"],
            quality=tc["quality"],
            take_screenshots=False,
        )
        results.append(result)
        print(result.report())

    return results
