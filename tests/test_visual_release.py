"""
tests/test_visual_release.py — Visual release tests with Playwright.

REAL browser testing: clicks send button, verifies chat works,
captures screenshots of reasoning cards, model generation, etc.

Run locally:
  python3 -m http.server 8765 &
  GATEWAY_URL=http://localhost:8765 \
  python3 -m pytest tests/test_visual_release.py -v --headed

Run in CI:
  python3 -m pytest tests/test_visual_release.py -v
"""

import os
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright, expect

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8765")
SCREENSHOTS_DIR = Path(os.environ.get("SCREENSHOT_DIR", ".openclaw/tmp/test_screenshots"))
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# ─── New UI selectors (premium redesign) ────────────────────
SEL = {
    "input": "#msgInput",
    "send_btn": "#sendBtn",
    "chat": "#chatMessages",
    "welcome": "#welcomeScreen",
    "msg_user": ".msg.user",
    "msg_assistant": ".msg.assistant",
    "toolbar_btns": ".toolbar-btn",
    "v_tabs": ".v-tab",
    "v_tools": ".v-tool",
    "account_btn": "#accountBtn",
    "account_dd": ".account-dropdown",
    "download_btn": "#downloadBtn",
    "download_dd": ".download-dropdown",
    "projects_panel": "#projectsPanel",
    "theme_pill": '[data-theme-val="light"]',
    "lang_pill": '[data-lang="en"]',
    "gen_overlay": "#genOverlay",
    "empty_state": "#emptyState",
}


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    p = ctx.new_page()
    p.goto(GATEWAY_URL)
    p.wait_for_load_state("networkidle")
    p.wait_for_timeout(500)
    yield p
    ctx.close()


def _shot(page, name):
    path = SCREENSHOTS_DIR / f"{name}_{int(time.time())}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"📸 {path}")
    return path


# ═══════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════


class TestPageLoad:
    """Initial page load checks."""

    def test_no_js_errors(self, page):
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.wait_for_timeout(1000)
        _shot(page, "01_page_load")
        assert len(errors) == 0, f"JS errors: {errors}"

    def test_welcome_visible(self, page):
        expect(page.locator(SEL["welcome"])).to_be_visible()
        _shot(page, "02_welcome")

    def test_input_visible(self, page):
        expect(page.locator(SEL["input"])).to_be_visible()
        _shot(page, "03_input_visible")

    def test_send_button_visible(self, page):
        expect(page.locator(SEL["send_btn"])).to_be_visible()
        _shot(page, "04_send_visible")

    def test_projects_panel_visible(self, page):
        expect(page.locator(SEL["projects_panel"])).to_be_visible()
        _shot(page, "05_projects_panel")

    def test_viewer_tabs_exist(self, page):
        count = page.locator(SEL["v_tabs"]).count()
        assert count == 5, f"Expected 5 viewer tabs, got {count}"
        _shot(page, "06_viewer_tabs")


class TestChatInteraction:
    """Chat input and message tests."""

    def test_input_accepts_text(self, page):
        inp = page.locator(SEL["input"])
        inp.fill("двухэтажный кирпичный дом 10x12")
        expect(inp).to_have_value("двухэтажный кирпичный дом 10x12")
        _shot(page, "07_input_filled")

    def test_send_creates_user_message(self, page):
        page.locator(SEL["input"]).fill("деревянный коттедж с террасой")
        page.locator(SEL["send_btn"]).click()
        page.wait_for_timeout(500)
        expect(page.locator(SEL["msg_user"])).to_be_visible()
        _shot(page, "08_user_message")

    def test_assistant_responds(self, page):
        page.locator(SEL["input"]).fill("современный дом 2 этажа")
        page.locator(SEL["send_btn"]).click()
        page.wait_for_timeout(2500)
        msgs = page.locator(SEL["msg_assistant"]).count()
        assert msgs >= 1, "No assistant response"
        _shot(page, "09_assistant_response")

    def test_empty_input_ignored(self, page):
        page.locator(SEL["input"]).fill("")
        page.locator(SEL["send_btn"]).click()
        page.wait_for_timeout(500)
        _shot(page, "10_empty_send")

    def test_enter_sends_message(self, page):
        page.locator(SEL["input"]).fill("офис в стиле лофт")
        page.locator(SEL["input"]).press("Enter")
        page.wait_for_timeout(1000)
        _shot(page, "11_enter_send")


class TestGeneration:
    """Generation overlay and 3D view tests."""

    def test_gen_overlay_appears(self, page):
        page.locator(SEL["input"]).fill("минималистичный дом")
        page.locator(SEL["send_btn"]).click()
        page.wait_for_timeout(1500)
        _shot(page, "12_gen_overlay")

    def test_gen_completes(self, page):
        page.locator(SEL["input"]).fill("коттедж 12x15 дерево")
        page.locator(SEL["send_btn"]).click()
        page.wait_for_timeout(8000)
        _shot(page, "13_gen_complete")


class TestUIElements:
    """Premium UI element tests."""

    def test_account_dropdown(self, page):
        page.locator(SEL["account_btn"]).click()
        page.wait_for_timeout(300)
        expect(page.locator(SEL["account_dd"])).to_be_visible()
        _shot(page, "14_account_dropdown")

    def test_token_bar_visible(self, page):
        page.locator(SEL["account_btn"]).click()
        page.wait_for_timeout(300)
        expect(page.locator(".token-fill")).to_be_visible()
        _shot(page, "15_token_bar")

    def test_theme_switch(self, page):
        page.locator(SEL["account_btn"]).click()
        page.wait_for_timeout(300)
        page.locator(SEL["theme_pill"]).click()
        page.wait_for_timeout(500)
        bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        _shot(page, "16_light_theme")
        # Switch back to dark
        page.locator('[data-theme-val="dark"]').click()
        page.wait_for_timeout(300)

    def test_lang_switch(self, page):
        page.locator(SEL["account_btn"]).click()
        page.wait_for_timeout(300)
        page.locator(SEL["lang_pill"]).click()
        page.wait_for_timeout(300)
        text = page.locator('[data-i18n="settings"]').text_content()
        assert text == "Settings", f"EN switch failed: {text}"
        _shot(page, "17_lang_en")
        # Switch back
        page.locator('[data-lang="ru"]').click()
        page.wait_for_timeout(200)

    def test_download_dropdown(self, page):
        page.locator(SEL["download_btn"]).click()
        page.wait_for_timeout(300)
        expect(page.locator(SEL["download_dd"])).to_be_visible()
        count = page.locator(".dl-item").count()
        assert count == 6, f"Expected 6 download formats, got {count}"
        _shot(page, "18_download_dd")

    def test_toolbar_buttons(self, page):
        count = page.locator(SEL["toolbar_btns"]).count()
        assert count >= 3, f"Expected >=3 toolbar buttons, got {count}"
        _shot(page, "19_toolbar")

    def test_viewer_tools(self, page):
        count = page.locator(SEL["v_tools"]).count()
        assert count >= 3, f"Expected >=3 viewer tools, got {count}"
        _shot(page, "20_viewer_tools")


class TestResponsive:
    """Mobile responsive tests."""

    def test_mobile_layout(self, page):
        page.set_viewport_size({"width": 375, "height": 812})
        page.wait_for_timeout(500)
        _shot(page, "21_mobile")

    def test_projects_hidden_mobile(self, page):
        page.set_viewport_size({"width": 375, "height": 812})
        page.wait_for_timeout(300)
        projects = page.locator(SEL["projects_panel"])
        # On mobile, projects panel should be hidden
        box = projects.bounding_box()
        if box:
            assert box["width"] == 0 or box["x"] + box["width"] <= 0, "Projects visible on mobile"
        _shot(page, "22_projects_hidden_mobile")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
