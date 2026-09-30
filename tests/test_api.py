from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_and_cases():
    assert client.get("/api/health").json()["status"] == "ok"
    response = client.get("/api/cases")
    assert response.status_code == 200
    assert len(response.json()) >= 30


def test_review_requires_prior_diagnosis():
    diagnose = client.post("/api/diagnose", json={"case_id": "CASE-003"})
    assert diagnose.status_code == 200

    response = client.post(
        "/api/cases/CASE-003/review",
        json={"status": "Accepted", "reviewer_name": "reviewer"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Accepted"
    assert body["diagnosis_snapshot"] is not None


def test_spreadsheet_endpoint():
    response = client.get("/api/spreadsheet")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 30
    first = data[0]
    for key in ("case_id", "title", "concept", "osi_layer", "severity", "symptom", "expected_fault", "ai_diagnosis", "status"):
        assert key in first

