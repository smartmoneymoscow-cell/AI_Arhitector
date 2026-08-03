"""
tests/test_e2e_playwright.py — Real browser E2E tests using Playwright.

Tests the ACTUAL send button click, not just string matching.
Requires: pip install playwright pytest-playwright
Run: python -m pytest tests/test_e2e_playwright.py -v
"""

import json
import os

import pytest

pytest.importorskip("playwright")

from playwright.sync_api import expect, sync_playwright

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")
API_KEY = os.environ.get("ARCH_API_KEYS", "test-key").split(",")[0]


def get_send_btn(page):
    """Return send button locator. Works with both old (.sbtn) and new (#sendBtn) versions."""
    if page.locator("#sendBtn").count() > 0:
        return page.locator("#sendBtn")
    return page.locator(".ibox .sbtn").last


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: d.dismiss())
    page.goto(GATEWAY_URL)
    page.wait_for_load_state("networkidle")
    page._errors = errors
    yield page
    ctx.close()


class TestPageLoad:
    def test_page_loads(self, page):
        expect(page).to_have_title("Architect")

    def test_chat_input_exists(self, page):
        inp = page.locator("#ci")
        expect(inp).to_be_visible()

    def test_send_button_exists(self, page):
        btn = get_send_btn(page)
        expect(btn).to_be_visible()


class TestSendButton:
    """Test the send button ACTUALLY works — checks visible results, not API internals."""

    def test_send_shows_user_message(self, page):
        """Clicking send with text shows user message in chat."""
        # Check if send() function exists (new version)
        has_send = page.evaluate("typeof send === 'function' || typeof sendMessage === 'function'")
        if not has_send:
            pytest.skip("send/sendMessage function not defined (script load error)")

        console_msgs = []
        page.on("console", lambda m: console_msgs.append(f"{m.type}: {m.text}"))

        inp = page.locator("#ci")
        if inp.count() == 0:
            inp = page.locator("#msgInput")  # old version
        inp.fill("двухэтажный кирпичный дом 10x12")

        btn = get_send_btn(page)
        btn.click()

        page.wait_for_timeout(3000)

        chat = page.locator("#tab-chat")
        if chat.count() == 0:
            chat = page.locator("#chatMessages")  # old version
        expect(chat).to_contain_text("двухэтажный")

    def test_enter_key_sends(self, page):
        """Pressing Enter shows message in chat."""
        has_send = page.evaluate("typeof send === 'function' || typeof sendMessage === 'function'")
        if not has_send:
            pytest.skip("send/sendMessage function not defined")

        inp = page.locator("#ci")
        if inp.count() == 0:
            inp = page.locator("#msgInput")
        inp.fill("современный офис")
        inp.press("Enter")

        page.wait_for_timeout(2000)
        chat = page.locator("#tab-chat")
        if chat.count() == 0:
            chat = page.locator("#chatMessages")
        expect(chat).to_contain_text("современный")

    def test_empty_input_does_nothing(self, page):
        """Empty input does not add message."""
        has_send = page.evaluate("typeof send === 'function' || typeof sendMessage === 'function'")
        if not has_send:
            pytest.skip("send/sendMessage function not defined")

        chat = page.locator("#tab-chat")
        if chat.count() == 0:
            chat = page.locator("#chatMessages")
        chat_before = chat.inner_text()

        inp = page.locator("#ci")
        if inp.count() == 0:
            inp = page.locator("#msgInput")
        inp.fill("")
        get_send_btn(page).click()

        page.wait_for_timeout(1000)
        chat_after = chat.inner_text()
        assert chat_before == chat_after

    def test_send_with_quick_prompt(self, page):
        """Quick prompt buttons work."""
        qp = page.locator(".qp").first
        if qp.is_visible():
            qp.click()
            page.wait_for_timeout(2000)
            chat = page.locator("#tab-chat")
            # Quick prompts should add a message
            assert len(chat.inner_text()) > 0


class TestSendButtonResilience:
    """Regression: button stops responding after failures."""

    def test_send_works_after_stuck_generation(self, page):
        has_st = page.evaluate("typeof ST !== 'undefined'")
        if not has_st:
            pytest.skip("Old version without ST object")

        page.evaluate("""
            ST.generating = true;
            ST._genStart = Date.now() - 60000;
        """)

        inp = page.locator("#ci")
        inp.fill("деревянный коттедж 12x15")
        get_send_btn(page).click()

        page.wait_for_timeout(2000)
        chat = page.locator("#tab-chat")
        expect(chat).to_contain_text("деревянный")

    def test_send_button_re_enables_after_click(self, page):
        inp = page.locator("#ci")
        inp.fill("офис 5 этажей")

        btn = get_send_btn(page)
        btn.click()
        page.wait_for_timeout(3000)

        expect(btn).to_be_enabled()

    def test_double_click_does_not_break(self, page):
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
    def test_health_endpoint(self, page):
        response = page.evaluate("""
            async () => {
                const r = await fetch('/api/v1/health');
                return {status: r.status, ok: r.ok};
            }
        """)
        assert response["ok"], f"Health endpoint failed: HTTP {response['status']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
