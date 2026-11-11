"""One model call for citation lines the regex parser cannot read confidently."""

import json
import re

import litellm

from retraction_agent.config import limits, load_config
from retraction_agent.llm import run_agent
from retraction_agent.normalize import normalize_doi, normalize_title
from retraction_agent.planning import (
    _SKIP_PREFIXES,
    _apa_parts,
    _attempted_citation,
    _citation_line,
    _dois_in,
)

_LIST = re.compile(r"^\d+[\).\]]\s+")
_LIST_MARKER = re.compile(r"^(?:\[\d+\]|\d+[\).\]]|[-*•·–—])\s+")
_HTTP = re.compile(r"https?://", re.IGNORECASE)
_BIBTEX = re.compile(
    r"^\s*@\w+\s*\{|\b(?:author|title|journal|booktitle|year|doi|url)\s*=\s*\{",
    re.IGNORECASE,
)
_FIELDS = ("title", "authors", "year", "venue", "doi", "url")

EXTRACT_PROMPT = """You extract citation fields from pasted lines. Call submit_extractions exactly once.

Copy text exactly as pasted. Never correct, complete, translate, or add anything.
Leave a field empty if it is not in the line.
Return one item for every line. Set raw_line_index to the index you were given.
"""

EXTRACT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_extractions",
            "description": "Return one extraction for every pasted line. Copy the line. Do not repair it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "raw_line_index": {"type": "integer"},
                                "title": {"type": "string"},
                                "authors": {"type": "string"},
                                "year": {"type": "string"},
                                "venue": {"type": "string"},
                                "doi": {"type": "string"},
                                "url": {"type": "string"},
                            },
                            "required": [
                                "raw_line_index",
                                "title",
                                "authors",
                                "year",
                                "venue",
                                "doi",
                                "url",
                            ],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    }
]


class _KeepRegex:
    """The model did not call the tool, so the regex reading stands."""


KEEP_REGEX = _KeepRegex()


def fallback_settings() -> dict:
    config = load_config()
    raw = config.get("llm_fallback") or {}
    try:
        max_lines = int(raw.get("max_lines") or 25)
    except (TypeError, ValueError):
        max_lines = 25
    try:
        temperature = float(raw["temperature"]) if raw.get("temperature") is not None else None
    except (TypeError, ValueError):
        temperature = None
    return {
        "enabled": bool(raw.get("enabled", False)),
        "max_lines": max(1, max_lines),
        "model": raw.get("model") or config["model"],
        "temperature": temperature,
    }


def fallback_complete(messages: list[dict], tools: list | None):
    """Production extractor call. Tests pass their own complete_fn instead."""
    config = load_config()
    settings = fallback_settings()
    kwargs = {
        "model": settings["model"],
        "vertex_location": config["vertex_location"],
        "messages": messages,
        "timeout": 45,
        "_skip_mcp_handler": True,
    }
    if settings["temperature"] is not None:
        kwargs["temperature"] = settings["temperature"]
    if tools:
        kwargs["tools"] = tools
    return litellm.completion(**kwargs).choices[0].message


def looks_like_author_list(text: str) -> bool:
    """True when the string is names and initials rather than a paper title."""
    if re.search(r"\bet al\.?\b", text or "", re.IGNORECASE):
        return True
    if "&" in (text or ""):
        return True
    if re.search(r"\b[A-Z][a-zA-Z'’\-]+,\s+[A-Z]\.", text or ""):
        return True
    parts = [part.strip() for part in (text or "").split(",") if part.strip()]
    return len(parts) >= 3 and all(len(part.split()) <= 3 for part in parts)


def is_confident(line: str) -> bool:
    """A DOI, or a (YYYY). title of at least 12 characters that is not an author list."""
    if _clean_dois(line):
        return True
    apa = _apa_parts(_body(line))
    if not apa:
        return False
    title = apa["title"]
    return len(title) >= 12 and not looks_like_author_list(title)


def is_hard(line: str) -> bool:
    """A pasted citation line that is not confident and is not an instruction."""
    body = _body(line)
    if not body or is_confident(line):
        return False
    if _ignorable(line):
        return False
    return True


def apply_llm_fallback(message: str, plan: dict, complete_fn) -> list[dict]:
    """Replace hard lines with validated model fields, or mark them unparsed."""
    if not fallback_settings()["enabled"]:
        return []
    lines = _lines(message)
    hard = [(index, line) for index, line in enumerate(lines) if is_hard(line)]
    if not hard:
        return []
    max_lines = fallback_settings()["max_lines"]
    sent = hard[:max_lines]
    overflow = hard[max_lines:]
    extracted, calls = _one_call(sent, complete_fn)
    if extracted is KEEP_REGEX:
        return calls
    replacements = {}
    for index, line in sent:
        if _rules_not_checkable(line):
            replacements[index] = _rules_not_checkable_ref(line)
        else:
            replacements[index] = extracted.get(index) or _unparsed(line)
    for index, line in overflow:
        if _rules_not_checkable(line):
            replacements[index] = _rules_not_checkable_ref(line)
        else:
            replacements[index] = _unparsed(line)
    plan["references"] = _merge_lines(lines, replacements, plan.get("references") or [])
    cap = limits()["max_references"]
    if len(plan["references"]) > cap:
        plan["references"] = plan["references"][:cap]
        plan["references_truncated"] = True
    return calls


def validate_items(sent: list[tuple[int, str]], items) -> dict[int, dict | None]:
    """Map each hard line to a ref, or None when that line's model output is discarded."""
    rejected = {index: None for index, _line in sent}
    if not isinstance(items, list) or len(items) != len(sent):
        return rejected
    by_index = {}
    expected = {index for index, _line in sent}
    for item in items:
        if not isinstance(item, dict):
            return rejected
        index = item.get("raw_line_index")
        if index not in expected or index in by_index:
            return rejected
        by_index[index] = item
    if set(by_index) != expected:
        return rejected
    out = {}
    for index, line in sent:
        out[index] = _accept_item(line, by_index[index])
    return out


def _one_call(sent: list[tuple[int, str]], complete_fn):
    box = {}

    def run_tool(name, args):
        if name != "submit_extractions":
            return json.dumps({"ok": False, "error": "unknown_tool"})
        items = args.get("items") if isinstance(args, dict) else None
        validated = validate_items(sent, items)
        box["validated"] = validated
        return json.dumps(
            {
                "ok": True,
                "parsed_by": "llm",
                "items": [
                    {
                        "raw_line_index": index,
                        "passed_copy_check": validated[index] is not None and not validated[index].get("unparsed"),
                        "parsed_by": "llm",
                    }
                    for index, _line in sent
                ],
            },
            ensure_ascii=False,
        )

    payload = {
        "lines": [
            {"raw_line_index": index, "line": _strip_list_marker(line)} for index, line in sent
        ]
    }
    messages = [
        {"role": "system", "content": EXTRACT_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    _text, calls = run_agent(
        messages,
        EXTRACT_TOOLS,
        run_tool,
        "citation-extractor",
        2,
        complete_fn,
    )
    if "validated" not in box:
        return KEEP_REGEX, calls
    return box["validated"], calls


def _accept_item(line: str, item: dict) -> dict | None:
    if _rules_not_checkable(line):
        return _rules_not_checkable_ref(line)
    source = _strip_list_marker(line)
    kept = {}
    for key in _FIELDS:
        value = item.get(key)
        if value is None:
            continue
        value = " ".join(str(value).split())
        if key == "title":
            value = _strip_list_marker(value)
        if not value:
            continue
        if not _appears(value, source):
            return None
        if key == "doi" and ("{" in value or "}" in value or not normalize_doi(value)):
            return None
        kept[key] = value
    ref = {"parsed_by": "llm"}
    doi = normalize_doi(kept.get("doi"))
    if doi:
        ref["doi"] = doi
    if kept.get("title"):
        ref["title"] = kept["title"]
    if kept.get("authors") and (ref.get("doi") or ref.get("title")):
        ref["author"] = kept["authors"]
    if kept.get("year") and (ref.get("doi") or ref.get("title")):
        ref["year"] = str(kept["year"])
    if not ref.get("doi") and _HTTP.search(ref.get("title") or ""):
        return {"not_checkable": True, "raw": _body(line)[:300], "parsed_by": "llm"}
    if ref.get("doi") or ref.get("title"):
        return ref
    if kept.get("url"):
        return {"not_checkable": True, "raw": _body(line)[:300], "parsed_by": "llm"}
    return None


def _merge_lines(lines: list[str], replacements: dict[int, dict], previous: list[dict]) -> list[dict]:
    ordered = []
    seen = set()
    for index, line in enumerate(lines):
        if index in replacements:
            batch = [replacements[index]]
        elif is_hard(line):
            batch = []
        else:
            batch = _citation_line(line)
        for ref in batch:
            key = _key(ref)
            if not key or key in seen:
                continue
            seen.add(key)
            ordered.append(ref)
    for ref in previous:
        key = _key(ref)
        if not key or key in seen or key in _hard_regex_keys(lines):
            continue
        seen.add(key)
        ordered.append(ref)
    return ordered


def _hard_regex_keys(lines: list[str]) -> set:
    keys = set()
    for line in lines:
        if not is_hard(line):
            continue
        for ref in _citation_line(line):
            key = _key(ref)
            if key:
                keys.add(key)
    return keys


def _key(ref: dict) -> str:
    return ref.get("doi") or normalize_title(ref.get("title") or "") or ref.get("raw") or ""


def _unparsed(line: str) -> dict:
    return {"raw": _body(line)[:300], "unparsed": True, "parsed_by": "llm"}


def _clean_dois(text: str) -> list[str]:
    return [doi for doi in _dois_in(text) if "{" not in doi and "}" not in doi]


def _strip_list_marker(text: str) -> str:
    """Drop a leading list marker. "5.", "5)", "[5]", "-", and a bullet all count."""
    value = str(text or "").strip()
    for _ in range(3):
        updated = _LIST_MARKER.sub("", value, count=1).strip()
        if updated == value:
            return value
        value = updated
    return value


def _rules_not_checkable(line: str) -> bool:
    return any(ref.get("not_checkable") for ref in _citation_line(line))


def _rules_not_checkable_ref(line: str) -> dict:
    for ref in _citation_line(line):
        if ref.get("not_checkable"):
            return {"not_checkable": True, "raw": str(ref.get("raw") or _body(line))[:300]}
    return {"not_checkable": True, "raw": _body(line)[:300]}


def _body(line: str) -> str:
    return _strip_list_marker(line).strip(" -*")


def _lines(message: str) -> list[str]:
    lines = [line.strip() for line in (message or "").splitlines() if line.strip()]
    if not lines and (message or "").strip():
        return [(message or "").strip()]
    return lines


def _ignorable(line: str) -> bool:
    body = _body(line)
    if _BIBTEX.search(body):
        return False
    numbered = bool(_LIST.match(line))
    if _attempted_citation(body, numbered):
        return False
    if re.search(r"https?://", body):
        return False
    return bool(body.endswith("?") or body.casefold().startswith(_SKIP_PREFIXES) or not _citation_line(line))


def _appears(value: str, line: str) -> bool:
    folded = _flat(value)
    return bool(folded) and folded in _flat(line)


def _flat(value: str) -> str:
    return " ".join(str(value).casefold().split())
