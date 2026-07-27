"""
Architect v10.2 — Backend API Tests
Run: pytest tests/test_server.py -v
"""

import json
import pytest


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════
@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    import sys
    import os

    # Ensure server module is importable
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    import server

    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


# ═══════════════════════════════════════════════════════════════
# Health endpoint
# ═══════════════════════════════════════════════════════════════
class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_health_returns_json(self, client):
        resp = client.get("/api/v1/health")
        data = json.loads(resp.data)
        assert "status" in data

    def test_health_status_ok(self, client):
        resp = client.get("/api/v1/health")
        data = json.loads(resp.data)
        assert data["status"] == "ok"


# ═══════════════════════════════════════════════════════════════
# Building parameter parser
# ═══════════════════════════════════════════════════════════════
class TestParseBuildingParams:
    """Test the Russian text → building params parser."""

    def test_import_server(self):
        import server

        assert hasattr(server, "parse_building_params")

    def test_parse_floors(self):
        from server import parse_building_params

        params = parse_building_params("двухэтажный дом")
        assert params.get("floors") == 2

    def test_parse_dimensions(self):
        from server import parse_building_params

        params = parse_building_params("дом 10×12")
        assert params.get("width") == 10 or params.get("W") == 10
        assert params.get("length") == 12 or params.get("L") == 12

    def test_parse_material_brick(self):
        from server import parse_building_params

        params = parse_building_params("кирпичный дом")
        assert params.get("facade_material") == "brick"

    def test_parse_material_wood(self):
        from server import parse_building_params

        params = parse_building_params("деревянный дом")
        assert params.get("facade_material") == "wood"

    def test_parse_roof_flat(self):
        from server import parse_building_params

        params = parse_building_params("дом с плоской кровлей")
        assert params.get("roof") == "flat" or params.get("roof_type") == "flat"

    def test_parse_roof_gabled(self):
        from server import parse_building_params

        params = parse_building_params("дом с двускатной кровлей")
        assert params.get("roof") == "gabled" or params.get("roof_type") == "gabled"


# ═══════════════════════════════════════════════════════════════
# Static file serving
# ═══════════════════════════════════════════════════════════════
class TestStaticFiles:
    def test_index_html_served(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_html_content_type(self, client):
        resp = client.get("/")
        assert "text/html" in resp.content_type


# ═══════════════════════════════════════════════════════════════
# Generate endpoint (smoke test — no actual Blender)
# ═══════════════════════════════════════════════════════════════
class TestGenerate:
    def test_generate_requires_post(self, client):
        resp = client.get("/api/v1/generate/building")
        assert resp.status_code in (405, 404)

    def test_generate_accepts_json(self, client):
        resp = client.post(
            "/api/v1/generate/building",
            json={"prompt": "двухэтажный кирпичный дом 10×12"},
            content_type="application/json",
        )
        # Should return something (200 or 500 if Blender not available)
        assert resp.status_code in (200, 500, 503)
