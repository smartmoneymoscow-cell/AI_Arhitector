"""
Architect v10.2 — Gateway Tests
Run: pytest tests/test_gateway.py -v
"""

import json
import pytest
import sys
import os


@pytest.fixture
def gateway_client():
    """Create a test client for the Gateway app."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "gateway"))

    import app as gateway_app

    gateway_app.app.config["TESTING"] = True
    with gateway_app.app.test_client() as c:
        yield c


class TestGatewayHealth:
    def test_health_endpoint(self, gateway_client):
        resp = gateway_client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_json(self, gateway_client):
        resp = gateway_client.get("/health")
        data = json.loads(resp.data)
        assert data["status"] == "ok"
        assert data["service"] == "gateway"
        assert "services" in data
