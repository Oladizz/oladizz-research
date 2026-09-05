import pytest
import os
import sys

# Ensure root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
pytest.importorskip("flask")
pytest.importorskip("trafilatura")
from api_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "healthy"
    assert "active_ai_provider" in data
    assert "supported_ais" in data
    assert "platform_support" in data


def test_dashboard_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Truth-Filtering Research Engine" in html
    assert "Active AI:" in html


def test_start_research_missing_topic(client):
    res = client.post("/api/research", json={})
    assert res.status_code == 400
    data = res.get_json()
    assert "error" in data


def test_start_research_queued(client):
    res = client.post("/api/research", json={"topic": "Test Quantum Computing", "max_urls": 2, "provider": "none"})
    assert res.status_code == 202
    data = res.get_json()
    assert "run_id" in data
    assert data["topic"] == "Test Quantum Computing"
    assert "status_url" in data
