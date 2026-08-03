"""
tests/test_e2e_playwright.py — E2E tests that verify ACTUAL send functionality.

CRITICAL: Tests must FAIL (not skip) when send() doesn't work.
"""
import os
import pytest

pytest.importorskip("playwright")
from playwright.sync_api import expect, sync_playwright

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")


def get_send_btn(page):
    """Return send button locator."""
    if page.locator("#sendBtn").count() > 0:
        return page.locator("#sendBtn")
    return page.locator(".ibox .sbtn").last


def get_input(page):
    """Return input field locator."""
    if page.locator("#ci").count() > 0:
        return page.locator("#ci")
    return page.locator("#msgInput")


def get_chat(page):
    """Return chat container locator."""
    if page.locator("#tab-chat").count() > 0:
        return page.locator("#tab-chat")
    return page.locator("#chatMessages")


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
    page.goto(GATEWAY_URL, timeout=30000)
    page.wait_for_load_state("networkidle")
    page._errors = errors
    yield page
    ctx.close()


class TestSendButtonActuallyWorks:
    """These tests FAIL if send() doesn't work. No skipping."""

    def test_script_parses_without_errors(self, page):
        """CRITICAL: JavaScript must parse without SyntaxError.

        This catches missing string concatenation, missing brackets,
        and any other syntax error that kills the entire script block.
        """
        js_errors = page._errors
        syntax_errors = [e for e in js_errors if 'SyntaxError' in e or 'Unexpected token' in e]
        assert len(syntax_errors) == 0, (
            f"JavaScript syntax error — send() won't exist!\n"
            f"Errors: {syntax_errors}\n"
            f"This means the entire <script> block failed to parse."
        )

    def test_send_function_exists(self, page):
        """send() or sendMessage() must be defined after page loads."""
        send_type = page.evaluate("typeof send")
        send_msg_type = page.evaluate("typeof sendMessage")
        assert send_type == 'function' or send_msg_type == 'function', (
            f"Neither send() nor sendMessage() is defined! "
            f"typeof send={send_type}, typeof sendMessage={send_msg_type}. "
            f"Script probably has a syntax error."
        )

    def test_send_adds_message_to_chat(self, page):
        """Clicking send with text MUST add user message to chat area."""
        inp = get_input(page)
        inp.fill("двухэтажный кирпичный дом 10x12")

        btn = get_send_btn(page)
        btn.click()

        page.wait_for_timeout(3000)

        chat = get_chat(page)
        chat_text = chat.inner_text()
        assert "двухэтажный" in chat_text, (
            f"Message NOT in chat after clicking send!\n"
            f"Chat content: {chat_text[:300]}\n"
            f"JS errors: {page._errors[:5]}"
        )

    def test_send_clears_input(self, page):
        """Input field must be cleared after sending."""
        inp = get_input(page)
        inp.fill("тестовое сообщение")

        get_send_btn(page).click()
        page.wait_for_timeout(1000)

        assert inp.input_value() == "", "Input not cleared after send"

    def test_enter_key_sends_message(self, page):
        """Pressing Enter must send message to chat."""
        inp = get_input(page)
        inp.fill("современный офис")
        inp.press("Enter")

        page.wait_for_timeout(3000)

        chat = get_chat(page)
        assert "современный" in chat.inner_text(), "Enter key didn't send message"

    def test_empty_input_does_nothing(self, page):
        """Empty input must not add message."""
        chat_before = get_chat(page).inner_text()

        inp = get_input(page)
        inp.fill("")
        get_send_btn(page).click()

        page.wait_for_timeout(1000)
        assert get_chat(page).inner_text() == chat_before

    def test_st_generating_not_stuck(self, page):
        """ST.generating must not be stuck true after page load."""
        has_st = page.evaluate("typeof ST !== 'undefined'")
        if not has_st:
            return  # Old version without ST
        generating = page.evaluate("ST.generating")
        assert not generating, f"ST.generating is stuck true: {generating}"

    def test_send_shows_thinking_or_response(self, page):
        """After send, some AI thinking or response must appear."""
        inp = get_input(page)
        inp.fill("деревянный коттедж 12x15")

        get_send_btn(page).click()
        page.wait_for_timeout(5000)

        chat = get_chat(page)
        chat_text = chat.inner_text()
        # Should have user msg + some AI response/thinking
        assert len(chat_text) > 50, (
            f"Chat too empty after send — no AI response.\n"
            f"Chat: {chat_text[:200]}"
        )


class TestPageBasics:
    def test_page_loads(self, page):
        expect(page).to_have_title("Architect")

    def test_input_exists(self, page):
        expect(get_input(page)).to_be_visible()

    def test_send_button_exists(self, page):
        expect(get_send_btn(page)).to_be_visible()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
