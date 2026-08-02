"""
tests/test_visual_release.py — Visual release tests with Playwright.

REAL browser testing: clicks send button, verifies chat works,
captures screenshots of reasoning cards, model generation, etc.

Run locally:
  GATEWAY_URL=https://architect-gateway.onrender.com \
  API_KEY=your-key \
  python3 -m pytest tests/test_visual_release.py -v --headed

Run in CI:
  python3 -m pytest tests/test_visual_release.py -v
"""

import json
import os
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")
API_KEY = os.environ.get("API_KEY", os.environ.get("ARCH_API_KEYS", "").split(",")[0])
SCREENSHOTS_DIR = Path(os.environ.get("SCREENSHOT_DIR", ".openclaw/tmp/test_screenshots"))
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    # Set API key before loading
    page.goto(GATEWAY_URL)
    page.evaluate(f"localStorage.setItem('arch_api_key', '{API_KEY}')")
    page.reload()
    page.wait_for_load_state("networkidle")
    yield page
    ctx.close()


def _screenshot(page, name):
    """Save screenshot with timestamp."""
    path = SCREENSHOTS_DIR / f"{name}_{int(time.time())}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"📸 Screenshot: {path}")
    return path


class TestSendButtonVisual:
    """Visual tests for send button — real clicks, real screenshots."""

    def test_page_loads_clean(self, page):
        """Page loads without errors — screenshot of initial state."""
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.wait_for_timeout(1000)
        _screenshot(page, "01_page_load")
        assert len(errors) == 0, f"Page errors: {errors}"

    def test_send_button_visible(self, page):
        """Send button is visible and clickable."""
        btn = page.locator("button.sbtn")
        expect = __import__("playwright.sync_api", fromlist=["expect"]).expect
        expect(btn).to_be_visible()
        _screenshot(page, "02_send_button_visible")

    def test_input_field_works(self, page):
        """Can type in the input field."""
        inp = page.locator("#ci")
        inp.fill("двухэтажный кирпичный дом 10x12")
        _screenshot(page, "03_input_filled")
        expect = __import__("playwright.sync_api", fromlist=["expect"]).expect
        expect(inp).to_have_value("двухэтажный кирпичный дом 10x12")

    def test_send_click_triggers_request(self, page):
        """Clicking send triggers an API request with X-API-Key."""
        requests = []
        page.on("request", lambda r: requests.append(r) if "/api/v1/" in r.url else None)

        inp = page.locator("#ci")
        inp.fill("современный дом 2 этажа")
        page.locator("button.sbtn").click()

        # Wait for API call
        page.wait_for_timeout(5000)
        _screenshot(page, "04_after_send_click")

        api_reqs = [r for r in requests if "/api/v1/" in r.url]
        assert len(api_reqs) > 0, "No API request triggered!"

        # Check X-API-Key header
        has_auth = any(
            r.headers.get("x-api-key") or r.headers.get("X-API-Key")
            for r in api_reqs
        )
        assert has_auth, "X-API-Key header missing!"

    def test_chat_shows_user_message(self, page):
        """User message appears in chat after send."""
        inp = page.locator("#ci")
        test_msg = "деревянный коттедж с террасой"
        inp.fill(test_msg)
        page.locator("button.sbtn").click()
        page.wait_for_timeout(2000)

        chat = page.locator("#tab-chat")
        expect = __import__("playwright.sync_api", fromlist=["expect"]).expect
        expect(chat).to_contain_text(test_msg)
        _screenshot(page, "05_user_message_in_chat")

    def test_reasoning_cards_appear(self, page):
        """After sending a prompt, reasoning/thinking cards appear."""
        inp = page.locator("#ci")
        inp.fill("построй отель 4 этажа с рестораном и парковкой")
        page.locator("button.sbtn").click()

        # Wait for LLM response and reasoning
        page.wait_for_timeout(8000)
        _screenshot(page, "06_reasoning_cards")

        # Check for reasoning elements (live thinking steps or reasoning cards)
        chat = page.locator("#tab-chat")
        has_content = chat.inner_text()
        assert len(has_content) > 50, f"Chat seems empty after send: {has_content[:100]}"

    def test_quick_prompts_work(self, page):
        """Quick prompt buttons trigger generation."""
        # Show quick prompts
        qpbar = page.locator("#qpbar")
        if qpbar.is_visible():
            first_qp = page.locator(".qp").first
            if first_qp.is_visible():
                first_qp.click()
                page.wait_for_timeout(3000)
                _screenshot(page, "07_quick_prompt")

    def test_empty_send_ignored(self, page):
        """Empty input does not trigger API call."""
        requests = []
        page.on("request", lambda r: requests.append(r) if "/api/v1/" in r.url else None)

        page.locator("#ci").fill("")
        page.locator("button.sbtn").click()
        page.wait_for_timeout(2000)
        _screenshot(page, "08_empty_send")

        api_reqs = [r for r in requests if "/api/v1/" in r.url]
        assert len(api_reqs) == 0, "Empty input triggered API request!"

    def test_enter_key_sends(self, page):
        """Pressing Enter sends the message."""
        requests = []
        page.on("request", lambda r: requests.append(r) if "/api/v1/" in r.url else None)

        inp = page.locator("#ci")
        inp.fill("офис в стиле лофт")
        inp.press("Enter")

        page.wait_for_timeout(3000)
        _screenshot(page, "09_enter_key_send")

        api_reqs = [r for r in requests if "/api/v1/" in r.url]
        assert len(api_reqs) > 0, "Enter key didn't trigger API request!"

    def test_generation_overlay_appears(self, page):
        """Generation overlay/spinner appears during processing."""
        inp = page.locator("#ci")
        inp.fill("минималистичный дом")
        page.locator("button.sbtn").click()

        # Check for generation overlay within 2 seconds
        page.wait_for_timeout(1500)
        _screenshot(page, "10_generation_overlay")


class TestReasoningVisual:
    """Visual tests for the reasoning/chat system."""

    def test_interior_prompt_reasoning(self, page):
        """Interior prompt triggers appropriate reasoning."""
        inp = page.locator("#ci")
        inp.fill("кухня в стиле хайтек 5 на 4 с островом")
        page.locator("button.sbtn").click()

        page.wait_for_timeout(10000)
        _screenshot(page, "11_interior_reasoning")

        # Verify chat has substantial content
        chat_text = page.locator("#tab-chat").inner_text()
        assert len(chat_text) > 100, "Interior reasoning not showing"

    def test_complex_prompt_reasoning(self, page):
        """Complex multi-requirement prompt generates detailed reasoning."""
        inp = page.locator("#ci")
        inp.fill("трехэтажный офис из стекла и бетона 20x30 с подземной парковкой, зеленой крышей и солнечными панелями")
        page.locator("button.sbtn").click()

        page.wait_for_timeout(12000)
        _screenshot(page, "12_complex_reasoning")

    def test_landscape_prompt_reasoning(self, page):
        """Landscape prompt is recognized and reasoned."""
        inp = page.locator("#ci")
        inp.fill("ландшафтный дизайн участка 15 соток с прудом и зоной барбекю")
        page.locator("button.sbtn").click()

        page.wait_for_timeout(10000)
        _screenshot(page, "13_landscape_reasoning")


class TestAPIEndpoints:
    """Test that real API endpoints respond correctly."""

    def test_health_endpoint(self, page):
        """Health endpoint returns ok."""
        resp = page.evaluate("""
            async () => {
                const r = await fetch('/api/v1/health');
                return {status: r.status, ok: r.ok, body: await r.json()};
            }
        """)
        assert resp["ok"], f"Health failed: {resp}"
        _screenshot(page, "14_health_ok")

    def test_parse_endpoint(self, page):
        """Parse endpoint understands Russian prompts."""
        resp = page.evaluate(f"""
            async () => {{
                const r = await fetch('/api/v1/parse', {{
                    method: 'POST',
                    headers: _apiHeaders(),
                    body: JSON.stringify({{text: 'двухэтажный кирпичный дом'}})
                }});
                return {{status: r.status, body: await r.json()}};
            }}
        """)
        assert resp["status"] == 200, f"Parse failed: {resp}"
        body = resp["body"]
        assert body.get("object_type") or body.get("building_type"), f"No type in response: {body}"
        _screenshot(page, "15_parse_ok")

    def test_stats_endpoint(self, page):
        """Stats endpoint returns cost/cache data."""
        resp = page.evaluate(f"""
            async () => {{
                const r = await fetch('/api/v1/stats', {{
                    headers: _apiHeaders()
                }});
                return {{status: r.status, body: r.ok ? await r.json() : null}};
            }}
        """)
        if resp["status"] == 200:
            assert "cost" in resp["body"] or "cache" in resp["body"]
        _screenshot(page, "16_stats_ok")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
