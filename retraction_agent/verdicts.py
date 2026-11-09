"""Verdicts are decided here, from tool results. The model does not choose them."""

import json
import re

from retraction_agent.citations import units
from retraction_agent.normalize import normalize_doi, normalize_title

FOOTER = (
    "No notice found never means a paper is reliable. This tool checks that a citation exists "
    "and matches, and whether a retraction or correction is on record. It does not check "
    "whether the paper supports your claim."
)

_FIX = {
    "CHECK FIRST",
    "WRONG LINK",
    "WRONG KIND OF LINK",
    "NOT FOUND",
    "COULD NOT VERIFY",
}
_CLEAR = {"NO NOTICE FOUND", "FOUND CAN'T CHECK RETRACTIONS"}
_WORD = re.compile(r"[a-z0-9]+")
_INSTRUCTION = (
    "Do not ",
    "Say ",
    "Call it",
    "writer_sentence",
    "record_status",
    "rw_lookup",
    "crossref_doi",
)
_STATUS_CODES = {
    "doi_not_registered",
    "doi_other_agency",
    "title_unverified",
    "identity_mismatch",
    "not_checkable",
    "exists_no_integrity_source",
    "registered_crossref",
    "extract_title_match",
    "registration_unchecked",
}
_TOOLISH = re.compile(
    r"\b(doi_agency|datacite_work|submit_plan|rw_pattern|rw_top_publishers|crossref_title)\b"
)
_REASON = {
    "Concerns/Issues about Data": "concerns about data",
    "Concerns/Issues about Image": "concerns about image",
    "Concerns/Issues about Results": "concerns about results",
    "Investigation by Journal/Publisher": "investigation by the journal or publisher",
    "Investigation by Third Party": "investigation by a third party",
    "Duplication of Data": "duplication of data",
    "Duplication of/in Image": "duplication of an image",
    "Duplication of Article": "duplication of an article",
    "Original Data and/or Images not Provided and/or not Available": "original data or images not provided",
    "Unreliable Data": "unreliable data",
    "Unreliable Results and/or Conclusions": "unreliable results or conclusions",
    "Upgrade/Update of Prior Notice(s)": "an update of an earlier notice",
    "Updated to Retraction": "updated to a retraction",
    "Legal Reasons and/or Threats": "legal reasons or threats",
    "Error in Analyses": "an error in the analyses",
    "Error in Methods": "an error in the methods",
    "Error in Results and/or Conclusions": "an error in the results or conclusions",
    "Falsification/Fabrication of Data": "falsification or fabrication of data",
    "Falsification/Fabrication of Image": "falsification or fabrication of an image",
    "Notice - Limited or No Information": "the notice has limited or no information",
}


def summary_line(verdicts: list[dict]) -> str:
    do_not = sum(item["label"] == "DO NOT CITE" for item in verdicts)
    fix = sum(item["label"] in _FIX for item in verdicts)
    clear = sum(item["label"] in _CLEAR for item in verdicts)
    paper = sum(item["label"] == "NOT A PAPER" for item in verdicts)
    return (
        f"{do_not} do not cite, {fix} need fixing or verifying, "
        f"{clear} no notice found or can't check, {paper} not a paper."
    )


def render_verdict_response(verdicts: list[dict]) -> str:
    lines = [
        summary_line(verdicts),
        "",
        "| # | Verdict | What we found | What to do |",
        "| --- | --- | --- | --- |",
    ]
    for item in verdicts:
        lines.append(
            f"| {item['n']} | {_cell(item['label'])} | {_cell(item['found'])} | {_cell(item['action'])} |"
        )
    lines.extend(["", FOOTER])
    return "\n".join(lines)


def labels_in(response: str) -> list[str]:
    labels = []
    for line in response.splitlines():
        if not line.startswith("|"):
            continue
        cells = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] == "#" or set(cells[0]) <= {"-", ":"}:
            continue
        labels.append(cells[1])
    return labels


def shares_half(query: str, title: str) -> bool:
    """True when at least half of the candidate title's words appear in the pasted title."""
    candidate = _words(title)
    pasted = set(_words(query))
    if not candidate or not pasted:
        return False
    shared = sum(1 for word in candidate if word in pasted)
    return shared * 2 >= len(candidate)


def select_candidates(query: str, candidates: list[dict], limit: int = 3) -> list[dict]:
    picked = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        if shares_half(query, candidate.get("title") or ""):
            picked.append(candidate)
        if len(picked) >= limit:
            break
    return picked


def prose_notes(text: str, limit: int | None = 3) -> str:
    """Keep plain sentences. Drop instructions, status codes, and tool names."""
    kept = []
    for unit in units(text or ""):
        if _instruction(unit):
            continue
        kept.append(unit.strip())
        if limit is not None and len(kept) >= limit:
            break
    return " ".join(kept).strip()


def build_verdicts(references: list[dict], calls: list[dict], snapshot_short: str) -> list[dict]:
    verdicts = []
    for index, ref in enumerate(references, start=1):
        verdicts.append(_one(index, ref, calls, snapshot_short))
    return verdicts


def _one(index: int, ref: dict, calls: list[dict], snapshot_short: str) -> dict:
    status = _status_for(ref, calls)
    code = status.get("status") or ""
    rows = _rows_for(ref, calls)
    work = _work_for(ref, calls)
    label, found, action = _decide(ref, code, status, rows, work, calls, snapshot_short)
    return {"n": index, "label": label, "found": found, "action": action}


def _decide(ref, code, status, rows, work, calls, snapshot_short) -> tuple[str, str, str]:
    short = snapshot_short
    if code == "not_checkable" or ref.get("not_checkable"):
        return (
            "NOT A PAPER",
            "This item is not a paper citation.",
            "This item was not checked as a paper.",
        )
    if code == "doi_not_registered":
        return (
            "NOT FOUND",
            "No registration agency has this DOI.",
            "This DOI may be mistyped or invented. It is not proof.",
        )
    if code == "identity_mismatch":
        return (
            "WRONG LINK",
            _mismatch_found(ref, status, short),
            "This link is a different paper from the pasted citation.",
        )
    notice = _notice_only(ref.get("doi"), rows)
    if notice:
        original = notice.get("original_doi") or "unavailable"
        title = notice.get("title") or "the original paper"
        return (
            "WRONG KIND OF LINK",
            f"This DOI is the retraction notice. {_watch(notice.get('record_id'), short)}".strip(),
            f"The link is the retraction notice. The original paper is {original}, {title}.",
        )
    retraction = _latest(rows, "retraction")
    if retraction or _nature_count(ref, calls, "Retraction"):
        return (
            "DO NOT CITE",
            _retraction_found(rows, retraction, calls, ref, short),
            "A retraction is on record for this citation.",
        )
    update = _retraction_update(work)
    if update and not retraction:
        return ("DO NOT CITE", _update_found(update, short, retraction=True), "A retraction is on record for this citation.")
    concern = _latest(rows, "expression of concern")
    correction = _latest(rows, "correction")
    reinstatement = _latest(rows, "reinstatement")
    if concern or correction or reinstatement:
        return (
            "CHECK FIRST",
            _check_found(concern, correction, reinstatement, short),
            "A notice other than a retraction is on record.",
        )
    other = _other_update(work)
    if other:
        return (
            "CHECK FIRST",
            _update_found(other, short, retraction=False),
            "A notice other than a retraction is on record.",
        )
    if code == "title_unverified":
        query = status.get("query") or ref.get("title") or ""
        close = select_candidates(query, _candidates(query, calls))
        action = (
            "The pasted title is not an exact match for one work."
            if close
            else "No close match found. Paste the full title, authors, and DOI."
        )
        return ("COULD NOT VERIFY", "The title could not be verified.", action)
    if code == "exists_no_integrity_source":
        return (
            "FOUND CAN'T CHECK RETRACTIONS",
            "The citation was found and matches. There is no retraction or correction source for this record, so integrity was not checked.",
            "The extract has no row for this record.",
        )
    if code == "doi_other_agency":
        return (
            "FOUND CAN'T CHECK RETRACTIONS",
            "The DOI is registered with another agency, and Crossref notices are unavailable for it.",
            "The extract has no row for this record.",
        )
    if code == "registration_unchecked" or _work_failed(work):
        return (
            "COULD NOT VERIFY",
            "The live registration or update check did not return.",
            "The missing live check is not proof that the paper is absent.",
        )
    return (
        "NO NOTICE FOUND",
        "The DOI is registered and nothing in the pasted citation disagreed. No notice is on record.",
        "This is not a guarantee of quality.",
    )


def _retraction_found(rows, retraction, calls, ref, short) -> str:
    if not retraction:
        record_id = _first_record_id(ref, calls)
        watched = _watch(record_id, short)
        return "A retraction is on record." if not watched else f"A retraction is on record. {watched}"
    parts = []
    earlier = _earlier_concern(rows, retraction)
    if earlier:
        when = earlier.get("retraction_date_iso") or earlier.get("retraction_date") or "an undated notice"
        parts.append(f"An expression of concern was recorded earlier, on {when}.")
    when = retraction.get("retraction_date_iso") or retraction.get("retraction_date") or "an undated notice"
    parts.append(f"The retraction is dated {when}.")
    reasons = _reasons(retraction.get("reasons") or [])
    if reasons:
        parts.append(f"The recorded reasons are {reasons}.")
    watched = _watch(retraction.get("record_id"), short)
    if watched:
        parts.append(watched)
    return " ".join(parts)


def _check_found(concern, correction, reinstatement, short) -> str:
    lead = concern or correction or reinstatement
    parts = []
    if reinstatement:
        when = reinstatement.get("retraction_date_iso") or reinstatement.get("retraction_date") or "an undated notice"
        original = reinstatement.get("original_date_iso") or reinstatement.get("original_date")
        sentence = f"This paper was reinstated on {when}."
        if original:
            sentence += f" The original date is {original}."
        parts.append(sentence)
    if lead and lead is not reinstatement:
        when = lead.get("retraction_date_iso") or lead.get("retraction_date") or "an undated notice"
        if lead is concern:
            parts.append(f"An expression of concern is on record, dated {when}.")
        else:
            parts.append(f"A correction is on record, dated {when}.")
    elif lead is reinstatement and not parts:
        parts.append("This paper was reinstated.")
    watched = _watch((lead or {}).get("record_id"), short)
    if watched:
        parts.append(watched)
    return " ".join(parts)


def _mismatch_found(ref, status, short) -> str:
    del short
    pasted = (status.get("pasted") or {}).get("title") or ref.get("title") or "the pasted citation"
    returned = status.get("returned") or {}
    title = returned.get("title") or "a different paper"
    author = returned.get("first_author") or "unknown first author"
    year = returned.get("year")
    year_text = str(year) if year not in {None, ""} else "unknown year"
    return (
        f"The pasted title is {pasted}. The DOI resolves to {title}, {author}, {year_text}."
    )


def _update_found(item: dict, short: str, retraction: bool) -> str:
    when = item.get("date") or "an undated notice"
    record_id = item.get("record_id")
    source = (item.get("source") or "").casefold()
    watch = "retraction" in source or "watch" in source
    if watch and record_id:
        lead = "The retraction" if retraction else "The update"
        return f"{lead} is dated {when}. {_watch(record_id, short)}"
    if retraction:
        return f"Crossref lists a retraction dated {when}."
    return f"Crossref lists an update dated {when}."


def _watch(record_id, short: str) -> str:
    del short
    if record_id:
        return f"Retraction Watch #{record_id}."
    return ""


def _earlier_concern(rows: list[dict], retraction: dict) -> dict | None:
    cutoff = retraction.get("retraction_date_iso") or ""
    earlier = [
        row
        for row in rows
        if _nature(row) == "expression of concern" and (row.get("retraction_date_iso") or "") < cutoff
    ]
    if not earlier or not cutoff:
        return None
    return _latest(earlier, "expression of concern")


def _latest(rows: list[dict], nature: str | None) -> dict | None:
    picked = [row for row in rows if nature is None or _nature(row) == nature]
    if not picked:
        return None
    return sorted(picked, key=lambda row: row.get("retraction_date_iso") or "")[-1]


def _nature(row: dict) -> str:
    return (row.get("nature") or "").casefold()


def _reasons(reasons: list) -> str:
    words = []
    for token in reasons:
        text = str(token or "").strip()
        if not text:
            continue
        words.append(_REASON.get(text, _fallback_reason(text)))
        if len(words) == 3:
            break
    if not words:
        return ""
    if len(words) == 1:
        return words[0]
    if len(words) == 2:
        return f"{words[0]} and {words[1]}"
    return ", ".join(words[:-1]) + f", and {words[-1]}"


def _fallback_reason(token: str) -> str:
    text = token.replace("/", " or ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1].lower() + text[1:] if text else text


def _notice_only(doi: str | None, rows: list[dict]) -> dict | None:
    norm = normalize_doi(doi)
    if not norm:
        return None
    notice = None
    for row in rows:
        if normalize_doi(row.get("original_doi")) == norm:
            return None
        if normalize_doi(row.get("retraction_doi")) == norm:
            notice = row
    return notice


def _retraction_update(work: dict) -> dict | None:
    for item in _updates(work):
        if "retract" in _blob(item):
            return item
    return None


def _other_update(work: dict) -> dict | None:
    updates = _updates(work)
    return updates[0] if updates else None


def _updates(work: dict) -> list[dict]:
    found = []
    for key in ("updated_by", "update_to"):
        for item in work.get(key) or []:
            if isinstance(item, dict):
                found.append(item)
    return found


def _blob(item: dict) -> str:
    return " ".join(str(item.get(key) or "") for key in ("type", "label", "source")).casefold()


def _work_failed(work: dict) -> bool:
    if not work:
        return False
    return work.get("ok") is False or bool(work.get("error"))


def _nature_count(ref, calls, nature: str) -> int:
    data = _lookup(ref, calls)
    return int((data.get("nature_counts") or {}).get(nature) or 0)


def _first_record_id(ref, calls):
    data = _lookup(ref, calls)
    ids = data.get("record_ids") or []
    return ids[0] if ids else None


def _rows_for(ref, calls) -> list[dict]:
    data = _lookup(ref, calls)
    rows = data.get("rows") or []
    return [row for row in rows if isinstance(row, dict)]


def _lookup(ref, calls) -> dict:
    doi = ref.get("doi")
    if doi:
        return _named(calls, "rw_lookup_doi", "doi", doi, normalize_doi)
    title = ref.get("title")
    if title:
        return _named(calls, "rw_lookup_title", "title", title, normalize_title)
    return {}


def _work_for(ref, calls) -> dict:
    doi = ref.get("doi")
    if not doi:
        return {}
    return _named(calls, "crossref_doi", "doi", doi, normalize_doi)


def _candidates(query: str, calls: list[dict]) -> list[dict]:
    data = _named(calls, "crossref_title", "title", query, normalize_title)
    return data.get("candidates") or []


def _status_for(ref, calls) -> dict:
    doi = normalize_doi(ref.get("doi"))
    title = normalize_title(ref.get("title") or "")
    raw = ref.get("raw") or ""
    for call in calls:
        if call.get("name") != "record_status":
            continue
        args = call.get("args") or {}
        if doi and normalize_doi(args.get("doi")) == doi:
            return _json(call)
        if not doi and title and normalize_title(args.get("title")) == title:
            return _json(call)
        if not doi and not title and raw and (args.get("raw") or "") == raw:
            return _json(call)
    return {}


def _named(calls, name, key, value, normalizer) -> dict:
    wanted = normalizer(value)
    for call in calls:
        if call.get("name") != name:
            continue
        if normalizer((call.get("args") or {}).get(key)) == wanted:
            return _json(call)
    return {}


def _json(call) -> dict:
    try:
        data = json.loads(call.get("result") or "")
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _words(value: str) -> list[str]:
    return _WORD.findall(normalize_title(value))


def _instruction(unit: str) -> bool:
    if any(piece in unit for piece in _INSTRUCTION):
        return True
    if _TOOLISH.search(unit):
        return True
    for match in re.findall(r"`([^`]+)`", unit):
        if match in _STATUS_CODES:
            return True
    return False


def _cell(value) -> str:
    return " ".join(str(value).replace("|", "/").split())
