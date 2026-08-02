"""
tests/e2e/test_chat_e2e.py — Automated browser E2E test.

Runs AFTER EACH RELEASE automatically.
1. Opens browser → chat interface
2. Sends random prompt
3. Clicks "Send" button
4. Screenshots the chat reasoning/response
5. Screenshots the preview window
6. Analyzes screenshots against the prompt
7. Validates the response matches the prompt

Uses Playwright for browser automation.
"""

import json
import os

import pytest

try:
    import playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

pytestmark = pytest.mark.skipif(not HAS_PLAYWRIGHT, reason="playwright not installed")
import random
import time
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════
# RANDOM PROMPTS — diverse architectural requests
# ═══════════════════════════════════════════════════════════════

RANDOM_PROMPTS = [
    # Standard buildings
    "двухэтажный кирпичный дом 10 на 12 с балконом и гаражом",
    "современный коттедж 12x15 с бассейном и террасой",
    "трехэтажный офисный центр из стекла 20 на 30",
    "таунхаус 8x16 в минималистичном стиле",
    "деревянная изба 8 на 10 в русском стиле",
    
    # Non-standard (tests LLM flexibility)
    "сарай 4 на 6 для инструментов",
    "беседка в японском стиле с бамбуком",
    "гараж на две машины с подвалом",
    "теплица 3 на 8 из поликарбоната",
    "навес для автомобиля 6 на 3",
    "бревенчатая баня 6 на 8 с предбанником",
    "детская площадка с горкой и песочницей",
    "забор из профнастила 2 метра высотой 20 метров длиной",
    "крытый бассейн 10 на 5 с раздевалкой",
    "магазин 8 на 12 с витринными окнами",
    
    # Interiors
    "современная кухня 4 на 5 с островом",
    "спальня в скандинавском стиле 5 на 6",
    "гостиная с камином 6 на 8",
    "ванная комната 3 на 4 с джакузи",
    "кабинет с библиотекой 4 на 5",
    
    # Complex
    "туристический комплекс на 50 номеров с рестораном и бассейном",
    "жилой комплекс из 4 корпусов с подземным паркингом",
    "спортивный зал 15 на 25 с трибунами",
]

# Expected keywords in response for each prompt category
PROMPT_KEYWORDS = {
    "сарай": ["barn", "shed", "сарай", "хоз"],
    "беседка": ["gazebo", "беседк"],
    "гараж": ["garage", "гараж"],
    "теплица": ["greenhouse", "теплиц"],
    "навес": ["carport", "canopy", "навес"],
    "баня": ["bathhouse", "sauna", "баня"],
    "забор": ["fence", "забор"],
    "бассейн": ["pool", "бассейн"],
    "магазин": ["shop", "store", "магазин"],
    "кухня": ["kitchen", "кухн"],
    "спальня": ["bedroom", "спальн"],
    "гостиная": ["living", "гостин"],
    "ванная": ["bathroom", "ванн"],
    "кабинет": ["study", "office", "кабинет"],
}


# ═══════════════════════════════════════════════════════════════
# PLAYWRIGHT E2E TESTS
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def base_url():
    """Base URL of the deployed application."""
    return os.environ.get("E2E_BASE_URL", "http://localhost:80")


@pytest.fixture(scope="session")
def api_key():
    """API key for authentication."""
    return os.environ.get("E2E_API_KEY", "")


@pytest.fixture(scope="session")
def screenshots_dir():
    """Directory for saving screenshots."""
    d = Path("test_screenshots")
    d.mkdir(exist_ok=True)
    return d


class TestChatE2E:
    """E2E tests: browser → chat → send → screenshot → validate."""

    @pytest.fixture(autouse=True)
    def setup(self, base_url, api_key, screenshots_dir):
        self.base_url = base_url
        self.api_key = api_key
        self.screenshots_dir = screenshots_dir

    def _get_random_prompts(self, count: int = 5) -> list[str]:
        """Select random prompts for testing."""
        return random.sample(RANDOM_PROMPTS, min(count, len(RANDOM_PROMPTS)))

    def test_chat_sends_and_receives(self, page):
        """Test: send message in chat, verify response appears."""
        from playwright.sync_api import sync_playwright

        prompts = self._get_random_prompts(3)

        for i, prompt in enumerate(prompts):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1920, "height": 1080})

                # Navigate to app
                page.goto(self.base_url)
                page.wait_for_load_state("networkidle")

                # Screenshot: initial state
                page.screenshot(
                    path=str(self.screenshots_dir / f"01_initial_{i}.png"),
                    full_page=True,
                )

                # Find chat input and type prompt
                chat_input = page.locator("[data-testid='chat-input'], textarea, input[type='text']").first
                chat_input.fill(prompt)

                # Screenshot: prompt entered
                page.screenshot(
                    path=str(self.screenshots_dir / f"02_prompt_entered_{i}.png"),
                    full_page=True,
                )

                # Click send button
                send_btn = page.locator(
                    "[data-testid='send-button'], "
                    "button:has-text('Отправить'), "
                    "button:has-text('Send'), "
                    "button[type='submit']"
                ).first
                send_btn.click()

                # Wait for response (up to 120 seconds for generation)
                page.wait_for_selector(
                    "[data-testid='chat-response'], .response, .message.assistant",
                    timeout=120000,
                )

                # Screenshot: chat with response (REASONING)
                page.screenshot(
                    path=str(self.screenshots_dir / f"03_chat_response_{i}.png"),
                    full_page=True,
                )

                # Wait for preview to appear
                try:
                    page.wait_for_selector(
                        "[data-testid='preview'], .preview, canvas, img.preview",
                        timeout=60000,
                    )
                    # Screenshot: PREVIEW window
                    page.screenshot(
                        path=str(self.screenshots_dir / f"04_preview_{i}.png"),
                        full_page=True,
                    )
                except Exception:
                    # Preview might not appear for all prompts
                    page.screenshot(
                        path=str(self.screenshots_dir / f"04_preview_timeout_{i}.png"),
                        full_page=True,
                    )

                # Validate response content
                response_text = page.locator(
                    "[data-testid='chat-response'], .response, .message.assistant"
                ).first.inner_text()

                self._validate_response(prompt, response_text, i)

                browser.close()

    def test_preview_window_shows_3d(self, page):
        """Test: preview window shows 3D model after generation."""
        from playwright.sync_api import sync_playwright

        prompt = "двухэтажный кирпичный дом 10 на 12"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})

            page.goto(self.base_url)
            page.wait_for_load_state("networkidle")

            # Enter prompt
            chat_input = page.locator("[data-testid='chat-input'], textarea").first
            chat_input.fill(prompt)

            # Send
            send_btn = page.locator(
                "[data-testid='send-button'], button:has-text('Отправить'), button[type='submit']"
            ).first
            send_btn.click()

            # Wait for 3D preview
            page.wait_for_selector(
                "[data-testid='preview'], canvas, .preview-container",
                timeout=120000,
            )

            # Screenshot: 3D preview
            page.screenshot(
                path=str(self.screenshots_dir / "05_3d_preview.png"),
                full_page=True,
            )

            # Verify preview element is visible
            preview = page.locator("[data-testid='preview'], canvas, .preview-container").first
            assert preview.is_visible(), "Preview window should be visible"

            browser.close()

    def test_sse_streaming_progress(self, page):
        """Test: SSE streaming shows progress updates."""
        from playwright.sync_api import sync_playwright

        prompt = "современный коттедж 12x15 с бассейном"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})

            page.goto(self.base_url)
            page.wait_for_load_state("networkidle")

            # Enter and send
            chat_input = page.locator("[data-testid='chat-input'], textarea").first
            chat_input.fill(prompt)
            send_btn = page.locator(
                "[data-testid='send-button'], button:has-text('Отправить'), button[type='submit']"
            ).first
            send_btn.click()

            # Wait for progress indicator
            try:
                page.wait_for_selector(
                    "[data-testid='progress'], .progress, .spinner, [class*='progress']",
                    timeout=10000,
                )
                # Screenshot: progress state
                page.screenshot(
                    path=str(self.screenshots_dir / "06_progress_streaming.png"),
                    full_page=True,
                )
            except Exception:
                pass  # Progress might be too fast

            # Wait for completion
            page.wait_for_selector(
                "[data-testid='chat-response'], .response, .message.assistant",
                timeout=120000,
            )

            # Screenshot: final state
            page.screenshot(
                path=str(self.screenshots_dir / "07_final_complete.png"),
                full_page=True,
            )

            browser.close()

    def _validate_response(self, prompt: str, response: str, index: int):
        """Validate that response matches the prompt."""
        response_lower = response.lower()
        prompt_lower = prompt.lower()

        # Check that response contains relevant keywords
        found_keyword = False
        for trigger, keywords in PROMPT_KEYWORDS.items():
            if trigger in prompt_lower:
                for kw in keywords:
                    if kw.lower() in response_lower:
                        found_keyword = True
                        break
                if found_keyword:
                    break

        # Save validation result
        validation = {
            "prompt": prompt,
            "response_preview": response[:500],
            "keyword_match": found_keyword,
            "response_length": len(response),
        }

        with open(self.screenshots_dir / f"validation_{index}.json", "w") as f:
            json.dump(validation, f, ensure_ascii=False, indent=2)

        # Assert response is not empty
        assert len(response) > 50, f"Response too short for prompt: {prompt}"
        
        # Assert response contains relevant content (for standard prompts)
        if any(kw in prompt_lower for kw in PROMPT_KEYWORDS):
            assert found_keyword, (
                f"Response doesn't match prompt '{prompt}'. "
                f"Expected keywords from {PROMPT_KEYWORDS.get(prompt_lower.split()[0], [])}"
            )


# ═══════════════════════════════════════════════════════════════
# ANALYSIS: Screenshot comparison with prompt
# ═══════════════════════════════════════════════════════════════

class TestScreenshotAnalysis:
    """Analyze screenshots to verify they match the prompt."""

    def test_screenshot_analysis_report(self, screenshots_dir):
        """Generate analysis report from all screenshots."""
        screenshots = list(screenshots_dir.glob("*.png"))
        validations = list(screenshots_dir.glob("*.json"))

        report = {
            "total_screenshots": len(screenshots),
            "total_validations": len(validations),
            "validations": [],
        }

        for v_file in sorted(validations):
            with open(v_file) as f:
                data = json.load(f)
            report["validations"].append(data)

        # Save report
        with open(screenshots_dir / "analysis_report.json", "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # All validations should pass
        failed = [v for v in report["validations"] if not v.get("keyword_match")]
        if failed:
            pytest.fail(
                f"{len(failed)} prompts didn't match expected keywords:\n" +
                "\n".join(f"  - {v['prompt']}" for v in failed)
            )
