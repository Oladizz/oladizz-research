import numpy as np
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


def test_pdf_endpoint_not_found(client):
    res = client.get("/api/research/nonexistent_run/pdf")
    assert res.status_code == 404


def test_pdf_endpoint_success(client):
    from api_server import RUNS
    test_run_id = "test_pdf_run_123"
    RUNS[test_run_id] = {
        "status": "completed",
        "report_md": "# Test Report\n\n- Fact 1: Battery density reached 500 Wh/kg."
    }
    res = client.get(f"/api/research/{test_run_id}/pdf")
    assert res.status_code == 200
    assert res.headers["Content-Type"] == "application/pdf"
    assert res.data.startswith(b"%PDF")


def test_stream_endpoint(client):
    from api_server import RUNS
    test_run_id = "test_stream_run_123"
    RUNS[test_run_id] = {
        "status": "completed",
        "progress": "Research dossier ready!",
        "report_md": "# Complete"
    }
    res = client.get(f"/api/research/{test_run_id}/stream")
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["Content-Type"]
    content = res.get_data(as_text=True)
    assert "completed" in content
