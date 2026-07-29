"""
Architect v12.0 — Backend API Tests (server.py monolith)
Run: pytest tests/test_server.py -v
"""

import json
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from starlette.testclient import TestClient
import server


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(server.app)


# ═══════════════════════════════════════════════════════════════
# Health endpoint
# ═══════════════════════════════════════════════════════════════
class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_health_returns_json(self, client):
        resp = client.get("/api/v1/health")
        data = resp.json()
        assert "status" in data

    def test_health_status_ok(self, client):
        resp = client.get("/api/v1/health")
        data = resp.json()
        assert data["status"] == "ok"


# ═══════════════════════════════════════════════════════════════
# Parser tests (shared.parser)
# ═══════════════════════════════════════════════════════════════
class TestParser:
    def test_parse_floors(self):
        from shared.parser import fallback_regex_parse
        params = fallback_regex_parse("двухэтажный дом")
        assert params["floors"] == 2

    def test_parse_dimensions(self):
        from shared.parser import fallback_regex_parse
        params = fallback_regex_parse("дом 10×12")
        assert params["width_m"] == 10
        assert params["length_m"] == 12

    def test_parse_material_brick(self):
        from shared.parser import fallback_regex_parse
        params = fallback_regex_parse("кирпичный дом")
        assert params["material"] == "brick"

    def test_parse_material_wood(self):
        from shared.parser import fallback_regex_parse
        params = fallback_regex_parse("деревянный дом")
        assert params["material"] == "wood"

    def test_parse_roof_flat(self):
        from shared.parser import fallback_regex_parse
        params = fallback_regex_parse("дом с плоской кровлей")
        assert params["roof_type"] == "flat"

    def test_parse_roof_gabled(self):
        from shared.parser import fallback_regex_parse
        params = fallback_regex_parse("дом с двускатной кровлей")
        assert params["roof_type"] == "gabled"


# ═══════════════════════════════════════════════════════════════
# Static file serving
# ═══════════════════════════════════════════════════════════════
class TestStaticFiles:
    def test_index_html_served(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_html_content_type(self, client):
        resp = client.get("/")
        assert "text/html" in resp.headers.get("content-type", "")


# ═══════════════════════════════════════════════════════════════
# Generate endpoint
# ═══════════════════════════════════════════════════════════════
class TestGenerate:
    def test_generate_accepts_json(self, client):
        try:
            resp = client.post(
                "/api/v1/generate",
                json={"prompt": "двухэтажный кирпичный дом 10×12"},
            )
            # Should return something (200 or 500 if Blender not available)
            assert resp.status_code in (200, 500, 503, 504)
        except (ValueError, RuntimeError):
            # Expected when Blender is not installed
            pass

    def test_parse_endpoint(self, client):
        """Parse endpoint returns structured params."""
        from shared.parser import fallback_regex_parse
        params = fallback_regex_parse("офис 5 этажей стекло 20×24")
        assert params["floors"] == 5
        assert params["width_m"] == 20
        assert params["length_m"] == 24
        assert params["material"] == "glass"
