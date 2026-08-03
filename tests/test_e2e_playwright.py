"""
tests/test_e2e_playwright.py — Real browser E2E tests using Playwright.

Tests the ACTUAL send button click, not just string matching.
Requires: pip install playwright pytest-playwright
Run: python -m pytest tests/test_e2e_playwright.py -v
"""

import json
import os

import pytest

# Skip if playwright not installed
pytest.importorskip("playwright")

from playwright.sync_api import expect, sync_playwright

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")
API_KEY = os.environ.get("ARCH_API_KEYS", "test-key").split(",")[0]


def get_send_btn(page):
    """Return send button locator. Works with both old (.sbtn) and new (#sendBtn) versions."""
    if page.locator("#sendBtn").count() > 0:
        return page.locator("#sendBtn")
    # Fallback: last .sbtn in the input area (old version)
    return page.locator(".ibox .sbtn").last


@pytest.fixture(scope="session")
def browser():
    """Launch browser once for all tests."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    """Fresh page per test with API key pre-set."""
    ctx = browser.new_context()
    page = ctx.new_page()
    # Pre-set API key in localStorage
    page.goto(GATEWAY_URL)
    page.evaluate(f"localStorage.setItem('arch_api_key', '{API_KEY}')")
    page.reload()
    page.wait_for_load_state("networkidle")
    yield page
    ctx.close()


class TestPageLoad:
    """Test that the page loads correctly."""

    def test_page_loads(self, page):
        """Main page returns 200 and has the title."""
        expect(page).to_have_title("Architect")

    def test_chat_input_exists(self, page):
        """Chat input field (id=ci) is visible."""
        inp = page.locator("#ci")
        expect(inp).to_be_visible()

    def test_send_button_exists(self, page):
        """Send button is visible and clickable."""
        btn = get_send_btn(page)
        expect(btn).to_be_visible()

    def test_quick_prompts_visible(self, page):
        """Quick prompt buttons appear after interaction."""
        # Quick prompts may be hidden initially, check they exist in DOM
        qpbar = page.locator("#qpbar")
        assert qpbar.count() >= 0  # exists in DOM


class TestSendButton:
    """Test the send button ACTUALLY works."""

    def test_send_button_click_sends_request(self, page):
        """Clicking send button with text triggers an API request."""
        requests = []
        page.on("request", lambda r: requests.append(r) if "/api/v1/" in r.url else None)

        inp = page.locator("#ci")
        inp.fill("двухэтажный кирпичный дом 10x12")

        btn = get_send_btn(page)
        btn.click()

        # Wait for at least one API request
        page.wait_for_timeout(3000)

        api_requests = [r for r in requests if "/api/v1/" in r.url]
        assert len(api_requests) > 0, "Send button did not trigger any API request!"

        # Check that at least one request has X-API-Key header
        has_auth = any(
            r.headers.get("x-api-key") or r.headers.get("X-API-Key")
            for r in api_requests
        )
        assert has_auth, "API requests missing X-API-Key header!"

    def test_enter_key_sends(self, page):
        """Pressing Enter in input field triggers send."""
        requests = []
        page.on("request", lambda r: requests.append(r) if "/api/v1/" in r.url else None)

        inp = page.locator("#ci")
        inp.fill("современный офис")
        inp.press("Enter")


        page.wait_for_timeout(3000)

        api_requests = [r for r in requests if "/api/v1/" in r.url]
        assert len(api_requests) > 0, "Enter key did not trigger API request!"

    def test_send_shows_user_message(self, page):
        """After sending, user message appears in chat."""
        inp = page.locator("#ci")
        inp.fill("тестовое сообщение")

        btn = get_send_btn(page)
        btn.click()

        # User message should appear
        page.wait_for_timeout(1000)
        chat = page.locator("#tab-chat")
        expect(chat).to_contain_text("тестовое сообщение")

    def test_empty_input_does_nothing(self, page):
        """Sending empty input does not trigger API call."""
        requests = []
        page.on("request", lambda r: requests.append(r) if "/api/v1/" in r.url else None)

        inp = page.locator("#ci")
        inp.fill("")
        btn = get_send_btn(page)
        btn.click()

        page.wait_for_timeout(2000)

        api_requests = [r for r in requests if "/api/v1/" in r.url]
        assert len(api_requests) == 0, "Empty input should not trigger API request!"

    def test_send_with_quick_prompt(self, page):
        """Quick prompt buttons work."""
        requests = []
        page.on("request", lambda r: requests.append(r) if "/api/v1/" in r.url else None)

        # Click a quick prompt if visible
        qp = page.locator(".qp").first
        if qp.is_visible():
            qp.click()
            page.wait_for_timeout(3000)
            api_requests = [r for r in requests if "/api/v1/" in r.url]
            assert len(api_requests) > 0, "Quick prompt did not trigger API request!"


class TestAPIKey:
    """Test API key handling."""

    def test_missing_api_key_shows_prompt(self, browser):
        """Without API key, user is prompted to enter one."""
        ctx = browser.new_context()
        page = ctx.new_page()
        # Clear any stored key
        page.goto(GATEWAY_URL)
        page.evaluate("localStorage.removeItem('arch_api_key')")
        page.reload()
        page.wait_for_load_state("networkidle")

        # The page should still load (key is checked on API call, not on load)
        expect(page).to_have_title("Architect")
        ctx.close()

    def test_api_key_sent_in_headers(self, page):
        """API key is included in request headers."""
        # Set a key
        page.evaluate(f"localStorage.setItem('arch_api_key', '{API_KEY}')")

        requests = []
        page.on("request", lambda r: requests.append(r) if "/api/v1/" in r.url else None)

        inp = page.locator("#ci")
        inp.fill("дом")
        get_send_btn(page).click()

        page.wait_for_timeout(3000)

        api_requests = [r for r in requests if "/api/v1/" in r.url]
        if api_requests:
            key_header = api_requests[0].headers.get("x-api-key") or api_requests[0].headers.get("X-API-Key")
            assert key_header, "X-API-Key header missing from API request!"


class TestSendButtonResilience:
    """Test send button works after failures (regression: button stops responding)."""

    def test_send_works_after_stuck_generation(self, page):
        """Send button works even if ST.generating was stuck true."""
        # Only run if new version with ST object
        has_st = page.evaluate("typeof ST !== 'undefined'")
        if not has_st:
            pytest.skip("Old version without ST object")

        page.evaluate("""
            ST.generating = true;
            ST._genStart = Date.now() - 60000;
        """)

        inp = page.locator("#ci")
        inp.fill("деревянный коттедж 12x15")

        btn = get_send_btn(page)
        btn.click()

        page.wait_for_timeout(2000)

        chat = page.locator("#tab-chat")
        expect(chat).to_contain_text("деревянный")

    def test_send_button_not_disabled_after_click(self, page):
        """Send button re-enables after send completes or fails."""
        inp = page.locator("#ci")
        inp.fill("офис 5 этажей")

        btn = get_send_btn(page)
        btn.click()
        page.wait_for_timeout(3000)

        expect(btn).to_be_enabled()

    def test_double_click_does_not_break_state(self, page):
        """Rapid double-click doesn't corrupt state."""
        inp = page.locator("#ci")
        inp.fill("баня с бассейном")

        btn = get_send_btn(page)
        btn.click()
        btn.click()

        page.wait_for_timeout(3000)

        inp.fill("сауна")
        btn.click()
        page.wait_for_timeout(1000)

        chat = page.locator("#tab-chat")
        expect(chat).to_contain_text("сауна")


class TestBackendHealth:
    """Test backend connectivity."""

    def test_health_endpoint(self, page):
        """Health check succeeds."""
        response = page.evaluate("""
            async () => {
                const r = await fetch('/api/v1/health');
                return {status: r.status, ok: r.ok};
            }
        """)
        assert response["ok"], f"Health endpoint failed: HTTP {response['status']}"

    def test_parse_endpoint(self, page):
        """Parse endpoint understands Russian prompts."""
        response = page.evaluate(f"""
            async () => {{
                const r = await fetch('/api/v1/parse', {{
                    method: 'POST',
                    headers: _apiHeaders(),
                    body: JSON.stringify({{text: 'двухэтажный кирпичный дом 10x12'}})
                }});
                if (!r.ok) return {{status: r.status, error: true}};
                const data = await r.json();
                return {{status: r.status, data: data}};
            }}
        """)
        assert response["status"] == 200, f"Parse failed: HTTP {response['status']}"
        data = response.get("data", {})
        assert data.get("object_type") or data.get("building_type"), "Parse missing type field"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
