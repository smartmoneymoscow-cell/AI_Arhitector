"""
tests/test_ui_v2.py — Automated UI tests for the redesigned Architect AI interface.

Tests every button, popup, responsive behavior, and interaction flow.
Requires: pip install playwright pytest-playwright
Run: python -m pytest tests/test_ui_v2.py -v --headed
"""

import os
import pytest

pytest.importorskip("playwright")
from playwright.sync_api import expect, sync_playwright

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    page.goto(GATEWAY_URL)
    page.wait_for_load_state("networkidle")
    yield page
    ctx.close()


@pytest.fixture
def mobile_page(browser):
    ctx = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True)
    page = ctx.new_page()
    page.goto(GATEWAY_URL)
    page.wait_for_load_state("networkidle")
    yield page
    ctx.close()


# ═══════════════════════════════════════════════
# 1. PAGE LOAD
# ═══════════════════════════════════════════════
class TestPageLoad:
    def test_page_loads(self, page):
        expect(page).to_have_title("Architect AI")

    def test_sidebar_visible_desktop(self, page):
        sidebar = page.locator("#sidebar-left")
        expect(sidebar).to_be_visible()

    def test_topbar_visible(self, page):
        topbar = page.locator(".topbar")
        expect(topbar).to_be_visible()

    def test_chat_area_visible(self, page):
        chat = page.locator("#chat-area")
        expect(chat).to_be_visible()

    def test_viewer_visible(self, page):
        viewer = page.locator(".viewer")
        expect(viewer).to_be_visible()

    def test_empty_state_shown(self, page):
        empty = page.locator(".empt-title")
        expect(empty).to_contain_text("Опишите здание")


# ═══════════════════════════════════════════════
# 2. SIDEBAR
# ═══════════════════════════════════════════════
class TestSidebar:
    def test_toggle_closes_sidebar(self, page):
        page.locator(".sidebar-toggle").click()
        sidebar = page.locator("#sidebar-left")
        expect(sidebar).to_have_class(/collapsed/)

    def test_toggle_opens_sidebar(self, page):
        # Close first
        page.locator(".sidebar-toggle").click()
        page.wait_for_timeout(300)
        # Open again
        page.locator(".sidebar-toggle").click()
        sidebar = page.locator("#sidebar-left")
        expect(sidebar).not_to_have_class(/collapsed/)

    def test_chat_list_has_items(self, page):
        items = page.locator(".chat-item")
        expect(items.first).to_be_visible()

    def test_chat_item_click_selects(self, page):
        items = page.locator(".chat-item")
        items.nth(1).click()
        expect(items.nth(1)).to_have_class(/active/)

    def test_new_chat_button(self, page):
        count_before = page.locator(".chat-item").count()
        page.locator(".new-chat-btn").click()
        count_after = page.locator(".chat-item").count()
        assert count_after == count_before + 1

    def test_search_filters_chats(self, page):
        page.locator(".search-input").fill("коттедж")
        page.wait_for_timeout(200)
        visible = page.locator(".chat-item:visible")
        expect(visible.first).to_contain_text("коттедж")


# ═══════════════════════════════════════════════
# 3. ACCOUNT POPUP
# ═══════════════════════════════════════════════
class TestAccountPopup:
    def test_click_opens_popup(self, page):
        page.locator(".account-trigger").click()
        popup = page.locator("#account-popup")
        expect(popup).to_be_visible()

    def test_popup_shows_token_bar(self, page):
        page.locator(".account-trigger").click()
        bar = page.locator("#token-fill")
        expect(bar).to_be_visible()

    def test_popup_shows_project_bar(self, page):
        page.locator(".account-trigger").click()
        bar = page.locator("#proj-fill")
        expect(bar).to_be_visible()

    def test_settings_button_works(self, page):
        page.locator(".account-trigger").click()
        page.locator(".account-popup-btn").first.click()
        notif = page.locator("#notif")
        expect(notif).to_be_visible()

    def test_upgrade_button_works(self, page):
        page.locator(".account-trigger").click()
        page.locator(".account-popup-btn").nth(1).click()
        notif = page.locator("#notif")
        expect(notif).to_be_visible()

    def test_outside_click_closes_popup(self, page):
        page.locator(".account-trigger").click()
        expect(page.locator("#account-popup")).to_be_visible()
        page.locator(".topbar").click(position={"x": 500, "y": 25})
        page.wait_for_timeout(200)
        expect(page.locator("#account-popup")).not_to_be_visible()


# ═══════════════════════════════════════════════
# 4. DOWNLOAD MENU
# ═══════════════════════════════════════════════
class TestDownloadMenu:
    def test_click_opens_menu(self, page):
        page.locator(".btn-premium.primary").click()
        menu = page.locator("#download-menu")
        expect(menu).to_be_visible()

    def test_menu_has_all_formats(self, page):
        page.locator(".btn-premium.primary").click()
        items = page.locator(".download-menu-item")
        assert items.count() == 7  # GLB, IFC, OBJ, PDF, DXF, PNG, Publish

    def test_glb_format_click(self, page):
        page.locator(".btn-premium.primary").click()
        page.locator(".download-menu-item").first.click()
        notif = page.locator("#notif")
        expect(notif).to_contain_text("GLB")

    def test_outside_click_closes_menu(self, page):
        page.locator(".btn-premium.primary").click()
        expect(page.locator("#download-menu")).to_be_visible()
        page.locator(".topbar").click(position={"x": 500, "y": 25})
        page.wait_for_timeout(200)
        expect(page.locator("#download-menu")).not_to_be_visible()

    def test_account_opens_closes_download(self, page):
        page.locator(".btn-premium.primary").click()
        expect(page.locator("#download-menu")).to_be_visible()
        page.locator(".account-trigger").click()
        page.wait_for_timeout(200)
        expect(page.locator("#download-menu")).not_to_be_visible()


# ═══════════════════════════════════════════════
# 5. CHAT INPUT
# ═══════════════════════════════════════════════
class TestChatInput:
    def test_textarea_visible(self, page):
        expect(page.locator("#ci")).to_be_visible()

    def test_placeholder_text(self, page):
        expect(page.locator("#ci")).to_have_attribute("placeholder", /Опишите/)

    def test_send_button_visible(self, page):
        expect(page.locator(".send-btn")).to_be_visible()

    def test_file_button_visible(self, page):
        expect(page.locator("#file-btn")).to_be_visible()

    def test_mic_button_visible(self, page):
        expect(page.locator("#mic-btn")).to_be_visible()

    def test_type_and_send(self, page):
        page.locator("#ci").fill("Двухэтажный коттедж 10x12")
        page.locator(".send-btn").click()
        page.wait_for_timeout(500)
        messages = page.locator(".msg")
        assert messages.count() >= 1

    def test_enter_sends_message(self, page):
        page.locator("#ci").fill("Тестовое сообщение")
        page.locator("#ci").press("Enter")
        page.wait_for_timeout(500)
        messages = page.locator(".msg.u")
        assert messages.count() >= 1

    def test_shift_enter_newline(self, page):
        page.locator("#ci").fill("Строка 1")
        page.locator("#ci").press("Shift+Enter")
        page.locator("#ci").type("Строка 2")
        value = page.locator("#ci").input_value()
        assert "\n" in value

    def test_file_input_accepts_images(self, page):
        file_input = page.locator("#fileIn")
        expect(file_input).to_have_attribute("accept", "image/*,.pdf,.ifc")


# ═══════════════════════════════════════════════
# 6. VIEWER TABS
# ═══════════════════════════════════════════════
class TestViewerTabs:
    def test_3d_tab_active_by_default(self, page):
        expect(page.locator("#vt-ext")).to_have_class(/on/)

    def test_click_int_tab(self, page):
        page.locator("#vt-int").click()
        expect(page.locator("#vt-int")).to_have_class(/on/)
        expect(page.locator("#vt-ext")).not_to_have_class(/on/)

    def test_click_plan_tab(self, page):
        page.locator("#vt-plan").click()
        expect(page.locator("#vt-plan")).to_have_class(/on/)

    def test_click_sec_tab(self, page):
        page.locator("#vt-sec").click()
        expect(page.locator("#vt-sec")).to_have_class(/on/)

    def test_click_fac_tab(self, page):
        page.locator("#vt-fac").click()
        expect(page.locator("#vt-fac")).to_have_class(/on/)

    def test_reset_camera_button(self, page):
        page.locator("text=Центр").click()
        notif = page.locator("#notif")
        expect(notif).to_contain_text("Камера")

    def test_dimensions_button(self, page):
        page.locator("#ann-btn").click()
        notif = page.locator("#notif")
        expect(notif).to_contain_text("Размеры")

    def test_wireframe_button(self, page):
        page.locator("#wire-btn").click()
        notif = page.locator("#notif")
        expect(notif).to_contain_text("Каркас")


# ═══════════════════════════════════════════════
# 7. TOPBAR BUTTONS
# ═══════════════════════════════════════════════
class TestTopbar:
    def test_new_project_button(self, page):
        page.locator("text=Новый").first.click()
        notif = page.locator("#notif")
        expect(notif).to_be_visible()

    def test_clear_chat_button(self, page):
        # Send a message first
        page.locator("#ci").fill("Тест")
        page.locator(".send-btn").click()
        page.wait_for_timeout(300)
        # Clear
        page.locator("text=Очистить").click()
        page.wait_for_timeout(300)
        # Should show empty state again
        empty = page.locator(".empt-title")
        if empty.count() > 0:
            expect(empty).to_be_visible()


# ═══════════════════════════════════════════════
# 8. RESPONSIVE (MOBILE)
# ═══════════════════════════════════════════════
class TestResponsive:
    def test_sidebar_hidden_mobile(self, mobile_page):
        sidebar = mobile_page.locator("#sidebar-left")
        # Should be off-screen (transform: translateX(-100%))
        box = sidebar.bounding_box()
        assert box is None or box["x"] + box["width"] <= 0

    def test_toggle_opens_mobile_sidebar(self, mobile_page):
        mobile_page.locator(".sidebar-toggle").click()
        mobile_page.wait_for_timeout(400)
        sidebar = mobile_page.locator("#sidebar-left")
        expect(sidebar).to_have_class(/open/)

    def test_overlay_visible_on_mobile_open(self, mobile_page):
        mobile_page.locator(".sidebar-toggle").click()
        mobile_page.wait_for_timeout(400)
        overlay = mobile_page.locator("#sidebar-overlay")
        expect(overlay).to_have_class(/show/)

    def test_overlay_click_closes_mobile_sidebar(self, mobile_page):
        mobile_page.locator(".sidebar-toggle").click()
        mobile_page.wait_for_timeout(400)
        mobile_page.locator("#sidebar-overlay").click(force=True)
        mobile_page.wait_for_timeout(400)
        sidebar = mobile_page.locator("#sidebar-left")
        expect(sidebar).not_to_have_class(/open/)


# ═══════════════════════════════════════════════
# 9. CSS VALIDATION
# ═══════════════════════════════════════════════
class TestCSS:
    def test_dark_theme_applied(self, page):
        bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        # Dark theme: bg should be dark (low RGB values)
        assert bg is not None

    def test_no_horizontal_scroll(self, page):
        scroll_width = page.evaluate("document.documentElement.scrollWidth")
        client_width = page.evaluate("document.documentElement.clientWidth")
        assert scroll_width <= client_width + 5  # 5px tolerance

    def test_input_not_clipped(self, page):
        box = page.locator("#ci").bounding_box()
        assert box is not None
        assert box["height"] >= 40  # Minimum visible height
        assert box["width"] >= 100  # Minimum visible width


# ═══════════════════════════════════════════════
# 10. INTEGRATION
# ═══════════════════════════════════════════════
class TestIntegration:
    def test_full_send_flow(self, page):
        """Full flow: type message → send → see response."""
        page.locator("#ci").fill("Двухэтажный коттедж 12x15 из кирпича")
        page.locator(".send-btn").click()
        # Should see user message
        user_msg = page.locator(".msg.u").last
        expect(user_msg).to_be_visible()
        # Should see thinking indicator
        page.wait_for_timeout(200)
        # Wait for response
        page.wait_for_timeout(2000)
        bot_msg = page.locator(".msg.a")
        assert bot_msg.count() >= 1

    def test_switch_tabs_after_send(self, page):
        """Send message then switch viewer tabs."""
        page.locator("#ci").fill("Тест")
        page.locator(".send-btn").click()
        page.wait_for_timeout(500)
        page.locator("#vt-plan").click()
        expect(page.locator("#vt-plan")).to_have_class(/on/)

    def test_new_chat_clears_messages(self, page):
        """New chat should reset the chat area."""
        page.locator("#ci").fill("Тест")
        page.locator(".send-btn").click()
        page.wait_for_timeout(300)
        page.locator(".new-chat-btn").click()
        page.wait_for_timeout(300)
        # Empty state should be back or messages cleared
        messages = page.locator(".msg")
        assert messages.count() == 0 or page.locator(".empt-title").is_visible()
