from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from config.settings import get_settings


def test_health_endpoint_liveness():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"


def test_ready_endpoint_reports_not_ready_without_required_config(monkeypatch):
    monkeypatch.setenv("WFM_DQ_MCP_SERVER_PATH_FOR_ADK", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("LLM_PROVIDER", "googlegenai")
    get_settings.cache_clear()

    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"
    get_settings.cache_clear()


def test_ready_endpoint_reports_ready_with_minimal_config(monkeypatch, tmp_path: Path):
    server_script = tmp_path / "server.py"
    server_script.write_text("# stub")

    monkeypatch.setenv("WFM_DQ_MCP_SERVER_PATH_FOR_ADK", str(server_script))
    monkeypatch.setenv("LLM_PROVIDER", "googlegenai")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    get_settings.cache_clear()

    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    get_settings.cache_clear()


def test_ready_endpoint_fails_when_sse_auth_required_but_token_missing(monkeypatch):
    monkeypatch.setenv("WFM_DQ_MCP_TRANSPORT_FOR_ADK", "sse")
    monkeypatch.setenv("WFM_DQ_MCP_SERVER_URL_FOR_ADK", "http://127.0.0.1:8000/sse")
    monkeypatch.setenv("WFM_DQ_MCP_REQUIRE_AUTH_FOR_SSE", "true")
    monkeypatch.setenv("WFM_DQ_MCP_AUTH_TOKEN_FOR_ADK", "")
    monkeypatch.setenv("LLM_PROVIDER", "googlegenai")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    get_settings.cache_clear()

    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"
    get_settings.cache_clear()
