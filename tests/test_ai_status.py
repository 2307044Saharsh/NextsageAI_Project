from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ai_status_reports_backends():
    response = client.get("/api/ai/status")
    assert response.status_code == 200
    body = response.json()
    assert "active_backend" in body
    assert "backends" in body
    assert any(item["name"] == "ollama" for item in body["backends"])
