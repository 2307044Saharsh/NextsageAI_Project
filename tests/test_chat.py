from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_open_question_without_case():
    response = client.post(
        "/api/chat",
        json={"message": "Why can my PC ping the gateway but not the server?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reply"]
    assert len(body["reasoning"]) >= 1
    assert body["case_context_used"] is False


def test_chat_with_case_context():
    response = client.post(
        "/api/chat",
        json={
            "message": "What should I check first for DHCP issues?",
            "case_id": "CASE-006",
            "include_case_context": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["case_context_used"] is True
    assert any("dhcp" in step.lower() or "gateway" in step.lower() for step in body["reasoning"] + [body["reply"]])


def test_chat_follow_up_history():
    first = client.post("/api/chat", json={"message": "Explain inter-VLAN routing simply."})
    assert first.status_code == 200
    second = client.post(
        "/api/chat",
        json={
            "message": "What show commands would prove it?",
            "history": [
                {"role": "user", "content": "Explain inter-VLAN routing simply."},
                {"role": "assistant", "content": first.json()["reply"]},
            ],
        },
    )
    assert second.status_code == 200
    assert second.json()["suggested_commands"]
