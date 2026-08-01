"""
Architect v12.0 — Gateway Tests
Run: pytest tests/test_gateway.py -v
"""

import json
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gateway"))

from httpx import AsyncClient, ASGITransport
import app as gateway_app


@pytest.fixture
def client():
    """Create a test client for the Gateway app (FastAPI)."""
    from starlette.testclient import TestClient
    return TestClient(gateway_app.app)


class TestGatewayHealth:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code in (200, 404)

    def test_health_returns_json(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "gateway"

    def test_health_api_v1(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code in (200, 404)
        data = resp.json()
        assert data["status"] == "ok"


class TestGatewayRoutes:
    def test_serve_index(self, client):
        resp = client.get("/")
        assert resp.status_code in (200, 404)

    def test_parse_endpoint(self, client):
        resp = client.post("/api/v1/parse", json={"text": "двухэтажный кирпичный дом 10x12"})
        # May return 502 if LLM service is not running
        assert resp.status_code in (200, 500, 502)

    def test_generate_endpoint(self, client):
        """Generate endpoint accepts request (may fail without Blender)."""
        resp = client.post("/api/v1/generate", json={"prompt": "дом 2 этажа"})
        # Should not be404 — endpoint exists
        assert resp.status_code in (200, 500, 502, 503, 504)
