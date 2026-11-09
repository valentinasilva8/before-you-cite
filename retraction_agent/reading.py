"""How each reference was read, for display. Lookups and verdicts stay as they are."""

import json
import re

from retraction_agent.normalize import normalize_doi, normalize_title

_URL = re.compile(r"https?://[^\s<>\"']+")
TITLE_MATCH_NOTE = "DOI found by title match, not in your paste"


def parsed_references_call(message: str, references: list[dict], calls: list[dict]) -> dict | None:
    items = parsed_reference_items(message, references, calls)
    if not items:
        return None
    return {
        "agent": "(harness)",
        "name": "parsed_references",
        "args": {},
        "result": json.dumps(items, ensure_ascii=False),
    }


def parsed_reference_items(message: str, references: list[dict], calls: list[dict]) -> list[dict]:
    """One item per reference, in verdict-row order, using the values the lookup used."""
    lines = pasted_lines(references, message)
    statuses = _statuses(calls)
    items = []
    for index, ref in enumerate(references or []):
        raw = lines[index] if index < len(lines) else ""
        title = str(ref.get("title") or "")
        authors = str(ref.get("author") or ref.get("authors") or "")
        year = ref.get("year")
        year_text = "" if year is None or year == "" else str(year)
        doi = normalize_doi(ref.get("doi")) or ""
        notes: list[str] = []
        adopted = _adopted_doi(ref, statuses[index] if index < len(statuses) else {}, calls)
        if adopted and not _doi_in_paste(adopted, raw):
            if not doi:
                doi = adopted
            notes.append(TITLE_MATCH_NOTE)
        items.append(
            {
                "raw": raw[:300],
                "title": title,
                "authors": authors,
                "year": year_text,
                "doi": doi,
                "url": _url_in(raw),
                "parsed_by": _parsed_by(ref),
                "notes": notes,
            }
        )
    return items


def pasted_lines(references: list[dict], message: str) -> list[str]:
    lines = [line.strip() for line in (message or "").splitlines() if line.strip()]
    chosen = [""] * len(references or [])
    used: set[int] = set()
    for index, ref in enumerate(references or []):
        best = _best_line(ref, lines, used)
        if best is None:
            continue
        chosen[index] = lines[best][:300]
        used.add(best)
    for index, ref in enumerate(references or []):
        if chosen[index]:
            continue
        best = _best_line(ref, lines, set())
        if best is not None:
            chosen[index] = lines[best][:300]
        else:
            chosen[index] = str(ref.get("raw") or "")[:300]
    return chosen


def _best_line(ref: dict, lines: list[str], skip: set[int]) -> int | None:
    best = None
    best_score = 0
    for index, line in enumerate(lines):
        if index in skip:
            continue
        score = _line_score(ref, line)
        if score > best_score:
            best_score = score
            best = index
    return best


def _line_score(ref: dict, line: str) -> int:
    raw = str(ref.get("raw") or "").strip()
    if raw and (raw == line or raw in line):
        return 5
    doi = normalize_doi(ref.get("doi"))
    if doi and doi.casefold() in line.casefold():
        return 4
    title = normalize_title(ref.get("title"))
    if title and title in normalize_title(line):
        return 3
    return 0


def _statuses(calls: list[dict]) -> list[dict]:
    found = []
    for call in calls or []:
        if call.get("name") != "record_status":
            continue
        found.append(_json(call.get("result")))
    return found


def _adopted_doi(ref: dict, status: dict, calls: list[dict]) -> str:
    matched = normalize_doi(status.get("matched_doi")) or ""
    if matched:
        return matched
    return _followed_doi(ref, calls)


def _followed_doi(ref: dict, calls: list[dict]) -> str:
    title = normalize_title(ref.get("title"))
    if not title or ref.get("doi"):
        return ""
    candidate = ""
    for call in calls or []:
        if call.get("name") != "crossref_title":
            continue
        if normalize_title((call.get("args") or {}).get("title")) != title:
            continue
        candidates = _json(call.get("result")).get("candidates") or []
        if candidates:
            candidate = normalize_doi(candidates[0].get("doi")) or ""
    if not candidate:
        return ""
    for call in calls or []:
        if call.get("name") != "rw_lookup_doi":
            continue
        args = call.get("args") or {}
        if not args.get("after_clear_title"):
            continue
        if normalize_doi(args.get("doi")) == candidate:
            return candidate
    return ""


def _doi_in_paste(doi: str, raw: str) -> bool:
    if not doi or not raw:
        return False
    text = raw.casefold()
    if doi.casefold() in text:
        return True
    suffix = doi.split("/", 1)[-1].casefold() if "/" in doi else ""
    return bool(suffix) and suffix in text


def _parsed_by(ref: dict) -> str:
    if ref.get("unparsed"):
        return "unreadable"
    if ref.get("parsed_by") == "llm":
        return "ai"
    return "rules"


def _url_in(text: str) -> str:
    match = _URL.search(text or "")
    if not match:
        return ""
    return match.group(0).rstrip(".,);]")


def _json(result) -> dict:
    try:
        data = json.loads(result or "")
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
