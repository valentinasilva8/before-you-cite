from fastapi.testclient import TestClient

from app import app
from retraction_agent.samples import PROMPTS


def test_health_and_page():
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["rows"] == 73597
    assert body["commit"].startswith("fb5f174f")
    assert body["sha256"] == "e5351ee51ab3f1da7fe98b3bd6c5c58049b8bff4705949ef6fd4f1a1315dd0ea"
    page = client.get("/")
    assert page.status_code == 200
    text = page.text
    assert "Before You Cite" in text
    assert "not a clean bill of health" in text
    assert "fb5f174f" in text
    samples = client.get("/samples").json()
    assert samples["prompts"] == PROMPTS


def test_chat_shape_and_session(monkeypatch):
    def fake(session, message, **kwargs):
        return {
            "response": "checked",
            "tool_calls": [
                {
                    "agent": "audit-researcher-1",
                    "name": "rw_lookup_doi",
                    "args": {"doi": "10.3390/nano10122325"},
                    "result": "{\"total\": 1}",
                }
            ],
        }

    monkeypatch.setattr("app.handle_turn", fake)
    client = TestClient(app)
    first = client.post("/chat", json={"message": "hello"}).json()
    assert set(first) == {"response", "session_id", "tool_calls"}
    call = first["tool_calls"][0]
    assert set(call) == {"agent", "name", "args", "result"}
    assert isinstance(call["result"], str)
    assert call["agent"] == "audit-researcher-1"
    second = client.post("/chat", json={"message": "again", "session_id": first["session_id"]}).json()
    assert second["session_id"] == first["session_id"]
    cleared = client.post(f"/clear?session_id={first['session_id']}")
    assert cleared.json()["status"] == "ok"
