"""Tool schemas and runners. Every result is a JSON string."""

import json

from retraction_agent.catalog import Catalog
from retraction_agent.crossref import CrossrefClient

AUDIT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "rw_lookup_doi",
            "description": (
                "Look up one DOI in the frozen Retraction Watch extract. Searches the original "
                "DOI and the notice DOI. Ignores blank and unavailable. Does not call Crossref."
            ),
            "parameters": {
                "type": "object",
                "properties": {"doi": {"type": "string"}},
                "required": ["doi"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rw_lookup_title",
            "description": (
                "Exact title lookup in the extract after whitespace collapse and casefold. "
                "A shortened title does not match. Does not call Crossref."
            ),
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        },
    },
]

PATTERN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "rw_pattern",
            "description": (
                "Count notice rows for one exact Journal string or one exact Publisher string. "
                "Not a rate. Do not correct the spelling. Pass the user's string."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "journal": {"type": "string"},
                    "publisher": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rw_top_publishers",
            "description": (
                "Rank publisher strings by notice rows. Include reason tokens and batch dates. "
                "Not a rate. Use limit 8 unless the user asked for a smaller list."
            ),
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
    },
]

CROSSREF_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "doi_agency",
            "description": (
                "Look up which registration agency holds this DOI. Call it after the extract lookup "
                "and before crossref_doi. A DOI that is not Crossref is not suspicious. "
                "A DOI no agency has is a signal to check by hand, not proof."
            ),
            "parameters": {
                "type": "object",
                "properties": {"doi": {"type": "string"}},
                "required": ["doi"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "datacite_work",
            "description": (
                "One public DataCite GET for a DOI that doi_agency said is not Crossref. "
                "Compare the returned title, first author, and year with the pasted citation. "
                "Do not call it for a Crossref DOI."
            ),
            "parameters": {
                "type": "object",
                "properties": {"doi": {"type": "string"}},
                "required": ["doi"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crossref_doi",
            "description": (
                "One Crossref GET for one DOI that doi_agency said is Crossref. "
                "Do not call it twice for the same DOI. Do not request an abstract. "
                "Call this only after the extract lookup and after doi_agency."
            ),
            "parameters": {
                "type": "object",
                "properties": {"doi": {"type": "string"}},
                "required": ["doi"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crossref_title",
            "description": (
                "One Crossref list call, query.bibliographic, for one title. "
                "If clear_match is false, do not treat a candidate as the paper."
            ),
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        },
    },
]

LEAD_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_plan",
            "description": (
                "Call this once. dispatch sends researchers. ask asks one question and does no research. "
                "Do not answer the citation question yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["dispatch", "ask"]},
                    "ask": {"type": "string"},
                    "references": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "doi": {"type": "string"},
                                "title": {"type": "string"},
                                "author": {"type": "string"},
                                "year": {"type": "string"},
                            },
                        },
                    },
                    "journals": {"type": "array", "items": {"type": "string"}},
                    "publishers": {"type": "array", "items": {"type": "string"}},
                    "top_publishers": {"type": "boolean"},
                    "limit": {"type": "integer"},
                },
                "required": ["action"],
            },
        },
    }
]


def audit_runner(catalog: Catalog):
    def run(name: str, args: dict) -> str:
        if name == "rw_lookup_doi":
            return _dump(catalog.lookup_doi(str(args.get("doi") or "")))
        if name == "rw_lookup_title":
            return _dump(catalog.lookup_title(str(args.get("title") or "")))
        return _dump({"ok": False, "error": "unknown_tool", "name": name})

    return run


def pattern_runner(catalog: Catalog):
    def run(name: str, args: dict) -> str:
        if name == "rw_pattern":
            journal = args.get("journal")
            publisher = args.get("publisher")
            return _dump(
                catalog.pattern(
                    journal=str(journal) if journal else None,
                    publisher=str(publisher) if publisher else None,
                )
            )
        if name == "rw_top_publishers":
            limit = args.get("limit")
            return _dump(catalog.top_publishers(None if limit is None else int(limit)))
        return _dump({"ok": False, "error": "unknown_tool", "name": name})

    return run


def crossref_runner(client: CrossrefClient, datacite=None):
    def run(name: str, args: dict) -> str:
        if name == "doi_agency":
            return client.doi_agency(str(args.get("doi") or ""))
        if name == "crossref_doi":
            return client.get_work(str(args.get("doi") or ""))
        if name == "crossref_title":
            return client.search_title(str(args.get("title") or ""))
        if name == "datacite_work":
            if datacite is None:
                return _dump({"ok": False, "error": "datacite_unavailable"})
            return datacite.get_work(str(args.get("doi") or ""))
        return _dump({"ok": False, "error": "unknown_tool", "name": name})

    return run


def lead_runner():
    def run(name: str, args: dict) -> str:
        if name != "submit_plan":
            return _dump({"ok": False, "error": "unknown_tool", "name": name})
        return _dump({"accepted": True, "action": args.get("action")})

    return run


def _dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)
