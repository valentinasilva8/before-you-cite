"""Round-2 gap summary for the lead: zero-row journal or publisher strings and the file strings near them."""

import json
import re

from retraction_agent.config import limits, load_config

LEAD_GAP_PROMPT = """You are the lead for Before You Cite, back for one more research round. You see only a summary the harness built from the first round, not the user chat.

Each gap is a journal or publisher string the user typed that matched 0 notice rows in the extract, with strings that do exist in the file and share its words.
Call submit_gap_plan exactly once.
- action "more" with tasks when a listed string is the same journal or publisher the user named, spelled the way the file spells it. Copy the string exactly from the list. At most {max_tasks} tasks.
- action "done" when no listed string is clearly the same one. A sister journal or a different imprint is not the same one.
Do not answer the question. Do not write a string that is not in the list.
"""

WRITER_GAP_NOTE = (
    "A later research round counted strings from the file that the lead judged to be the name the user typed. "
    "Say the user's string matched 0 notice rows, then give each file string exactly as written with its count."
)

LEAD_GAP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_gap_plan",
            "description": (
                "Call this once. more sends one pattern researcher per task. done stops. "
                "Each task string must be copied from the candidates in the summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["more", "done"]},
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string", "enum": ["journal", "publisher"]},
                                "string": {"type": "string"},
                            },
                            "required": ["field", "string"],
                        },
                    },
                },
                "required": ["action"],
            },
        },
    }
]

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "of", "and", "for", "in", "on", "a", "an"}


class GapAbort(Exception):
    """Any problem in the gap round. The caller drops the whole round."""


def gap_settings() -> dict:
    """Off unless config/config.json turns it on. Code ceilings hold even if the config is mistyped."""
    raw = load_config().get("gap_round") or {}
    rounds = int(limits().get("max_research_rounds") or 1)
    return {
        "enabled": raw.get("enabled") is True,
        "extra_rounds": max(0, min(rounds - 1, 2)),
        "max_tasks": max(1, min(int(raw.get("max_tasks", 3)), 5)),
        "max_candidates": max(1, min(int(raw.get("max_candidates", 5)), 8)),
        "researcher_tool_rounds": max(1, min(int(raw.get("researcher_tool_rounds", 2)), 3)),
        "lead_timeout_s": max(0.01, min(float(raw.get("lead_timeout_s", 20)), 30)),
        "researcher_timeout_s": max(0.01, min(float(raw.get("researcher_timeout_s", 20)), 30)),
        "budget_s": max(0.01, min(float(raw.get("budget_s", 45)), 60)),
        "skip_after_s": max(0.0, min(float(raw.get("skip_after_s", 60)), 90)),
    }


def _words(text: str) -> set[str]:
    return {word for word in _WORD.findall((text or "").casefold()) if word not in _STOP}


def candidate_strings(catalog, field: str, query: str, limit: int) -> list[dict]:
    """File strings whose words contain the query's words, or cover at least half of them."""
    index = catalog.by_journal if field == "journal" else catalog.by_publisher
    want = _words(query)
    if not want:
        return []
    found = []
    for name, ids in index.items():
        if name == query:
            continue
        have = _words(name)
        if not have:
            continue
        if want <= have:
            rank = 0
        elif have <= want and 2 * len(have) >= len(want):
            rank = 1
        else:
            continue
        found.append((rank, len(want ^ have), -len(ids), name))
    found.sort()
    return [{"string": name, "rows": -neg} for _, _, neg, name in found[:limit]]


def tried_strings(calls: list[dict]) -> set[tuple[str, str]]:
    tried = set()
    for call in calls:
        if call.get("name") != "rw_pattern":
            continue
        args = call.get("args") or {}
        for field in ("journal", "publisher"):
            if args.get(field):
                tried.add((field, str(args[field])))
    return tried


def find_gaps(calls: list[dict], catalog, limit: int) -> list[dict]:
    """Zero-row strings the casefold retry could not fix, with candidates not looked up yet."""
    tried = tried_strings(calls)
    gaps = []
    seen = set()
    for call in calls:
        if call.get("name") != "rw_pattern":
            continue
        try:
            data = json.loads(call.get("result") or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict) or not data.get("ok") or data.get("rows") or data.get("casefold_unique"):
            continue
        field = data.get("field")
        query = data.get("matched")
        if field not in {"journal", "publisher"} or not query or (field, query) in seen:
            continue
        seen.add((field, query))
        options = [
            item
            for item in candidate_strings(catalog, field, query, limit)
            if (field, item["string"]) not in tried
        ]
        if options:
            gaps.append({"field": field, "string": query, "rows": 0, "candidates": options})
    return gaps


def validate_gap_plan(args, gaps: list[dict], tried: set, max_tasks: int) -> tuple[str, list[dict], dict]:
    """Return (action, tasks, record). Raise GapAbort on anything malformed or empty."""
    if not isinstance(args, dict):
        raise GapAbort("args not an object")
    action = args.get("action")
    if action == "done":
        return "done", [], {"action": "done", "accepted": [], "rejected": [], "dropped_over_cap": 0}
    if action != "more":
        raise GapAbort(f"bad action {action!r}")
    raw_tasks = args.get("tasks")
    if not isinstance(raw_tasks, list):
        raise GapAbort("tasks not a list")
    allowed = {(gap["field"], item["string"]) for gap in gaps for item in gap["candidates"]}
    accepted, rejected, keys = [], [], set()
    for item in raw_tasks:
        if not isinstance(item, dict):
            rejected.append({"task": str(item)[:200], "why": "not an object"})
            continue
        key = (item.get("field"), item.get("string"))
        if key not in allowed:
            rejected.append({"task": item, "why": "not a listed candidate"})
        elif key in tried or key in keys:
            rejected.append({"task": item, "why": "already looked up"})
        else:
            keys.add(key)
            accepted.append({"field": key[0], "string": key[1]})
    dropped = max(0, len(accepted) - max_tasks)
    accepted = accepted[:max_tasks]
    if not accepted:
        raise GapAbort("more with no valid task")
    record = {"action": "more", "accepted": accepted, "rejected": rejected, "dropped_over_cap": dropped}
    return "more", accepted, record


def lead_gap_runner():
    def run(name: str, args: dict) -> str:
        if name != "submit_gap_plan":
            return json.dumps({"ok": False, "error": "unknown_tool", "name": name})
        return json.dumps({"accepted": True})

    return run
