"""One run_agent loop: fresh messages, own tools, own round cap."""

import json

import litellm

from retraction_agent.config import load_config

litellm.suppress_debug_info = True


def complete(messages: list[dict], tools: list | None):
    config = load_config()
    kwargs = {
        "model": config["model"],
        "vertex_location": config["vertex_location"],
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
    # Ordinary function tools. Skip LiteLLM's MCP handler, which imports the mcp package.
    kwargs["_skip_mcp_handler"] = True
    kwargs["timeout"] = 45
    return litellm.completion(**kwargs).choices[0].message


def run_agent(messages: list[dict], tools: list | None, run_tool, agent: str, max_rounds: int, complete_fn) -> tuple[str, list[dict]]:
    """Append each reply, run the tools the model asked for, and stop when it answers in text."""
    tool_calls: list[dict] = []
    if max_rounds < 1:
        max_rounds = 1
    for _ in range(max_rounds):
        reply = complete_fn(messages, tools)
        messages.append(reply.model_dump())
        if not getattr(reply, "tool_calls", None):
            return reply.content or "", tool_calls
        for call in reply.tool_calls:
            args = _args(call.function.arguments)
            try:
                result = run_tool(call.function.name, args)
            except Exception as exc:
                result = json.dumps({"ok": False, "error": type(exc).__name__, "detail": str(exc)[:300]})
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)
            tool_calls.append({"agent": agent, "name": call.function.name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    return "Tool-round cap reached before the model stopped calling tools.", tool_calls


def _args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
