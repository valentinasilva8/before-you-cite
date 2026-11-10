from fastapi.testclient import TestClient

from app import app
from retraction_agent.samples import PROMPTS
from tests.fakes import scripted_complete


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
    assert "not proof the paper is sound" in text
    assert "fb5f174f" in text
    samples = client.get("/samples").json()
    assert samples["prompts"] == PROMPTS


def test_static_files_send_no_cache():
    client = TestClient(app)
    for path in ("/static/app.js", "/static/styles.css"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
    page = client.get("/")
    assert page.headers["cache-control"] == "no-store"
    assert "Edit and recheck" not in page.text
    assert 'class="info-boxes"' in page.text
    assert "styles.css?v=11" in page.text
    assert "app.js?v=11" in page.text
    assert 'id="send"' not in page.text
    assert ">Ask<" not in page.text


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


def test_publisher_chat_keeps_the_response_shape(monkeypatch):
    monkeypatch.setattr(
        "retraction_agent.orchestrate.default_complete",
        scripted_complete("The writer must not invent these counts."),
    )
    client = TestClient(app)
    body = client.post("/chat", json={"message": PROMPTS["publisher_question"]}).json()
    assert set(body) == {"response", "session_id", "tool_calls"}
    assert isinstance(body["session_id"], str) and body["session_id"]
    assert "Hindawi: 11,524 notice rows" in body["response"]
    assert "PLoS: 1,805 notice rows" in body["response"]
    assert "The writer must not invent these counts." not in body["response"]
    assert body["tool_calls"]
    for call in body["tool_calls"]:
        assert set(call) == {"agent", "name", "args", "result"}
        assert isinstance(call["agent"], str)
        assert isinstance(call["name"], str)
        assert isinstance(call["args"], dict)
        assert isinstance(call["result"], str)
