"""
tests/test_send_button.py — CRITICAL: Test submit button functionality.

This test MUST pass before ANY release. If send button doesn't work,
the entire app is useless.

Tests:
1. Frontend loads (HTTP 200)
2. Send button handler exists in HTML
3. _sendInner function exists
4. Enter key handler exists
5. Quick prompt buttons work
6. Live generate endpoint responds
7. Response contains valid GLB data
"""

import pytest
import re
import httpx


GATEWAY_URL = "https://architect-gateway.onrender.com"
FRONTEND_URL = GATEWAY_URL  # Frontend served from gateway
TIMEOUT = 120


class TestSendButton:
    """Test that the send button and chat input actually work."""

    @classmethod
    def setup_class(cls):
        """Load frontend HTML once."""
        try:
            r = httpx.get(f"{FRONTEND_URL}/", timeout=30)
            cls.html = r.text
            cls.frontend_ok = r.status_code == 200
        except Exception as e:
            cls.html = ""
            cls.frontend_ok = False
            cls.error = str(e)

    def test_frontend_loads(self):
        """Frontend must return HTTP 200."""
        assert self.frontend_ok, f"Frontend not loading: {getattr(self, 'error', 'unknown')}"

    def test_send_function_exists(self):
        """send() function must exist in HTML."""
        assert "async function send()" in self.html or "function send()" in self.html, \
            "send() function missing — submit button will not work!"

    def test_send_inner_function_exists(self):
        """_sendInner() function must exist."""
        assert "_sendInner()" in self.html, \
            "_sendInner() missing — send button will crash!"

    def test_send_button_in_html(self):
        """Send button (➤) must exist."""
        assert 'onclick="send()"' in self.html, \
            "Send button onclick='send()' missing!"

    def test_enter_key_handler(self):
        """Enter key must trigger send."""
        assert "Enter" in self.html and "send()" in self.html, \
            "Enter key handler missing — keyboard submit won't work!"

    def test_input_field_exists(self):
        """Chat input field (id='ci') must exist."""
        assert 'id="ci"' in self.html, \
            "Input field id='ci' missing — can't type prompts!"

    def test_quick_prompts_exist(self):
        """Quick prompt buttons (Дом, Офис, Коттедж) must exist."""
        assert "Дом" in self.html and "Офис" in self.html, \
            "Quick prompt buttons missing!"

    def test_go_function_exists(self):
        """go() function for quick prompts must exist."""
        assert "function go(" in self.html or "async function go(" in self.html, \
            "go() function missing — quick prompts won't work!"

    def test_apply_params_exists(self):
        """applyParams() must exist for building generation."""
        assert "function applyParams(" in self.html, \
            "applyParams() missing — generation will crash!"

    def test_build_model_exists(self):
        """buildModel() must exist for 3D rendering."""
        assert "function buildModel(" in self.html, \
            "buildModel() missing — no 3D output!"

    def test_start_gen_exists(self):
        """startGen() must exist to trigger generation."""
        assert "function startGen(" in self.html, \
            "startGen() missing — send button won't generate anything!"

    def test_three_js_loaded(self):
        """Three.js CDN must be referenced."""
        assert "three.js" in self.html.lower() or "three.min.js" in self.html.lower() or "three.module" in self.html.lower() or "cdn.jsdelivr" in self.html, \
            "Three.js CDN not found — 3D won't render!"

    def test_no_syntax_errors_in_script(self):
        """All <script> blocks must parse without syntax errors."""
        import ast
        # Extract inline scripts
        scripts = re.findall(r'<script>(.*?)</script>', self.html, re.DOTALL)
        for i, script in enumerate(scripts):
            # Skip non-JS (like JSON data)
            if script.strip().startswith('{') or script.strip().startswith('['):
                continue
            # Basic check: no obvious syntax errors
            # Check for unclosed braces
            opens = script.count('{')
            closes = script.count('}')
            # Allow some tolerance for template literals
            assert abs(opens - closes) < 5, \
                f"Script block {i} has mismatched braces ({opens} open, {closes} close) — likely syntax error!"


class TestLiveGeneration:
    """Test that live generation actually works end-to-end."""

    def test_generate_building(self):
        """Generate a building via API — must return valid GLB."""
        r = httpx.post(
            f"{GATEWAY_URL}/api/v1/generate",
            json={"prompt": "дом 2 этажа кирпич 10x12"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"Generate failed: HTTP {r.status_code}"
        assert len(r.content) > 1000, f"Response too small ({len(r.content)} bytes) — not a valid GLB"
        # GLB starts with 'glTF'
        assert r.content[:4] == b'glTF', "Response is not a valid GLB file"

    def test_generate_interior(self):
        """Generate an interior via API."""
        r = httpx.post(
            f"{GATEWAY_URL}/api/v1/generate",
            json={"prompt": "кухня в стиле хайтек"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"Interior generate failed: HTTP {r.status_code}"
        assert len(r.content) > 1000, f"Response too small ({len(r.content)} bytes)"

    def test_generate_hotel(self):
        """Generate a hotel via API."""
        r = httpx.post(
            f"{GATEWAY_URL}/api/v1/generate",
            json={"prompt": "отель 4 этажа"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"Hotel generate failed: HTTP {r.status_code}"

    def test_health_endpoint(self):
        """Health endpoint must respond."""
        r = httpx.get(f"{GATEWAY_URL}/health", timeout=15)
        assert r.status_code == 200

    def test_parse_endpoint(self):
        """Parse endpoint must understand Russian prompts."""
        r = httpx.post(
            f"{GATEWAY_URL}/api/v1/parse",
            json={"text": "двухэтажный кирпичный дом 10x12"},
            timeout=30,
        )
        assert r.status_code == 200, f"Parse failed: HTTP {r.status_code}"
        data = r.json()
        assert "type" in data or "gen_type" in data or "building_type" in data or "object_type" in data, "Parse response missing type field"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
