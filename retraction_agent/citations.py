"""Keep record ids, DOIs, and the snapshot commit tied to tool results."""

import json
import re

from retraction_agent.normalize import normalize_doi

_DOI = re.compile(r"10\.\d{4,9}/[^\s)\]>,;\"']+", re.IGNORECASE)
_RECORD = re.compile(r"\brecord(?:\s+id)?\s*[:#]?\s*(\d{3,8})\b", re.IGNORECASE)
_COMMIT = re.compile(r"\b[0-9a-f]{8,40}\b", re.IGNORECASE)
_QUALITY = re.compile(
    r"\b(the paper is fine|this paper is fine|the work is fine|safe to cite|\bsafe\b|"
    r"the paper is reliable|the work is reliable|it is reliable|so it is fine|"
    r"has not been retracted|hasn't been retracted|has never been retracted|fabricat\w*)\b",
    re.IGNORECASE,
)
_QUALITY_EXCEPTION = re.compile(
    r"data limit|not a judgment|not a clean|does not mean|not proof|not safe|never safe|"
    r"could not verify|existence and integrity|integrity was not checked|not a claim|by hand",
    re.IGNORECASE,
)
_STATUS = re.compile(
    r"\b(retracted|retraction|correction|expression of concern|record\s+\d+)\b",
    re.IGNORECASE,
)
_GUESS_EXCEPTION = re.compile(r"not confirmed|not an exact|not cited|do not cite|candidate", re.IGNORECASE)


def corpus_from(results: list[str], snapshot: str) -> dict:
    text = "\n".join(results).lower()
    dois = set()
    for match in _DOI.findall(text):
        norm = normalize_doi(match)
        if norm:
            dois.add(norm)
    return {"text": text, "dois": dois, "snapshot": snapshot.lower(), "short": snapshot.lower()[:8]}


def enforce_citations(answer: str, results: list[str], snapshot: str, pending: list[dict], regenerate) -> str:
    """Regenerate once when a cited id is not in the tool results, then drop the leftover sentences."""
    corpus = corpus_from(results, snapshot)
    problems = problems_in(answer, corpus, pending)
    if problems and regenerate is not None:
        revised = regenerate(answer, problems)
        if isinstance(revised, str) and revised.strip():
            answer = revised
        problems = problems_in(answer, corpus, pending)
    if problems:
        answer = strip_units(answer, corpus, pending)
    return answer.strip()


def problems_in(answer: str, corpus: dict, pending: list[dict]) -> list[str]:
    found = []
    for doi in dois_in(answer):
        if doi not in corpus["dois"]:
            found.append(f"DOI {doi} is not in the tool results")
    for record_id in records_in(answer):
        if record_id not in corpus["text"]:
            found.append(f"record {record_id} is not in the tool results")
    for token in commits_in(answer):
        if not commit_ok(token, corpus):
            found.append(f"commit {token} is not the snapshot in the tool results")
    if quality_problem(answer):
        found.append("a sentence treats absence as the paper being fine, reliable, or not retracted")
    if guess_problem(answer, pending):
        found.append("a sentence cites an unconfirmed title candidate")
    return found


def strip_units(answer: str, corpus: dict, pending: list[dict]) -> str:
    kept = [unit for unit in units(answer) if keep_unit(unit, corpus, pending)]
    return "\n".join(kept).strip()


def keep_unit(unit: str, corpus: dict, pending: list[dict]) -> bool:
    if _bad_quality(unit):
        return False
    if _cites_guess(unit, pending):
        return False
    if any(doi not in corpus["dois"] for doi in dois_in(unit)):
        return False
    if any(record_id not in corpus["text"] for record_id in records_in(unit)):
        return False
    if any(not commit_ok(token, corpus) for token in commits_in(unit)):
        return False
    return True


def units(text: str) -> list[str]:
    chunks = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.count("|") >= 2:
            # A markdown table row stays whole, so no cell is left over as a sentence with a stray "|".
            chunks.append(line)
            continue
        parts = re.split(r"(?<=[.!?])\s+", line)
        chunks.extend(part for part in parts if part)
    return chunks


def dois_in(text: str) -> list[str]:
    found = []
    for match in _DOI.findall(text):
        norm = normalize_doi(match)
        if norm:
            found.append(norm)
    return found


def records_in(text: str) -> list[str]:
    return _RECORD.findall(text)


def commits_in(text: str) -> list[str]:
    stripped = _DOI.sub(" ", text.lower())
    return _COMMIT.findall(stripped)


def commit_ok(token: str, corpus: dict) -> bool:
    token = token.lower()
    snapshot = corpus["snapshot"]
    short = corpus["short"]
    if snapshot.startswith(token) or token.startswith(short):
        return short in corpus["text"] or snapshot in corpus["text"]
    return False


def quality_problem(answer: str) -> bool:
    return any(_bad_quality(unit) for unit in units(answer))


def _bad_quality(unit: str) -> bool:
    if _QUALITY_EXCEPTION.search(unit):
        return False
    return bool(_QUALITY.search(unit))


def guess_problem(answer: str, pending: list[dict]) -> bool:
    return any(_cites_guess(unit, pending) for unit in units(answer))


def _cites_guess(unit: str, pending: list[dict]) -> bool:
    dois = _pending_dois(pending)
    if not dois:
        return False
    lowered = unit.lower()
    if not any(doi in lowered for doi in dois):
        return False
    if _GUESS_EXCEPTION.search(unit):
        return False
    return bool(_STATUS.search(unit))


def _pending_dois(pending: list[dict]) -> set[str]:
    found = set()
    for item in pending:
        for candidate in item.get("candidates") or []:
            doi = normalize_doi(candidate.get("doi"))
            if doi:
                found.add(doi)
    return found


CONFIRM_NOTE = "Confirm which title you meant. The choices are listed under the table."


def confirmation_question(pending: list[dict]) -> str:
    lines = []
    for item in pending:
        lines.append(f"Query: {item.get('query')}")
        for index, candidate in enumerate(item.get("candidates") or [], start=1):
            title = " ".join(str(candidate.get("title") or "(no title)").split())
            lines.append(f"{index}. {title}")
            doi = " ".join(str(candidate.get("doi") or "").split())
            if doi:
                lines.append(f"DOI: {doi}")
    return "\n".join(lines)


def grounded_fallback(tool_calls: list[dict], snapshot_short: str) -> str:
    """Used only when citation stripping leaves the answer empty. Fields come from tool JSON."""
    lines = []
    for call in tool_calls:
        try:
            data = json.loads(call["result"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        if call["name"] == "rw_lookup_doi" and data.get("total") == 0:
            lines.append(
                f"No record in the Retraction Watch extract {snapshot_short} for "
                f"{data.get('query_doi')} (0 rows). No record is a data limit."
            )
        if call["name"] == "rw_lookup_doi":
            for row in data.get("rows") or []:
                reasons = "; ".join(row.get("reasons") or [])
                lines.append(
                    f"Record {row.get('record_id')} nature {row.get('nature')} "
                    f"notice date {row.get('retraction_date')} "
                    f"notice DOI {row.get('retraction_doi_raw') or 'none'} "
                    f"reasons {reasons} journal {row.get('journal')} "
                    f"publisher {row.get('publisher')} snapshot {snapshot_short}."
                )
    return "\n".join(lines).strip()
