import litellm

from retraction_agent.llm import complete

_TOOL = {
    "type": "function",
    "function": {
        "name": "ping",
        "description": "ping",
        "parameters": {"type": "object", "properties": {}},
    },
}


def test_tool_completion_does_not_import_mcp(monkeypatch):
    real = litellm.completion

    def wrapped(**kwargs):
        forwarded = dict(kwargs)
        forwarded["model"] = "gpt-4o-mini"
        forwarded["mock_response"] = "ok"
        return real(**forwarded)

    monkeypatch.setattr(litellm, "completion", wrapped)
    message = complete([{"role": "user", "content": "hi"}], tools=[_TOOL])
    assert message.content
