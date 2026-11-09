"""Registration and identity checks. These run before any retraction wording."""

import json
import re

from retraction_agent.normalize import normalize_doi, normalize_title

_RETRACTED = re.compile(r"^\s*retracted\s*:\s*", re.IGNORECASE)
_ET_AL = re.compile(r",?\s+et al\.?$", re.IGNORECASE)

EXISTS_NO_INTEGRITY = (
    "found and matches the citation; we have no retraction or correction source for arXiv, "
    "so integrity was not checked."
)

SCOPE = (
    "This check covers whether the citation exists and whether the returned record matches "
    "the pasted text. It does not say whether the paper supports a claim made about it."
)

STATUS_NOTES = {
    "doi_not_registered": (
        "No registration agency has this DOI. That is a signal to check the citation by hand. It is not proof."
    ),
    "doi_other_agency": (
        "This DOI is registered with an agency other than Crossref. Crossref notices are unavailable for it. "
        "The local extract was checked by DOI. An empty extract row is not a clean bill of health."
    ),
    "title_unverified": (
        "There is no DOI, and there is no confident Crossref title match. "
        "The citation could not be verified."
    ),
    "identity_mismatch": (
        "The DOI resolves to a record whose title, first author, or year differs from the pasted citation. "
        "Both sides are in this result."
    ),
    "not_checkable": "This item has no DOI and no title, so it was not checked.",
    "exists_no_integrity_source": EXISTS_NO_INTEGRITY,
    "registered_crossref": "The DOI is registered with Crossref.",
    "extract_title_match": "The pasted title matches one row in the local extract.",
    "registration_unchecked": (
        "The agency lookup did not return, so registration was not decided. The extract lookup still ran."
    ),
}


def titles_agree(pasted, returned) -> bool:
    left = bare_title(pasted)
    right = bare_title(returned)
    return bool(left) and left == right


def bare_title(value) -> str:
    return _RETRACTED.sub("", normalize_title(value)).strip()


def first_family(author: str | None) -> str | None:
    if not author:
        return None
    text = " ".join(str(author).split())
    text = _ET_AL.sub("", text).strip(" .")
    if "," in text:
        family = text.split(",", 1)[0].strip()
    else:
        parts = text.split()
        family = parts[-1] if parts else ""
    family = family.strip(".")
    return family or None


def compare_identity(pasted: dict, returned: dict) -> dict:
    """Compare pasted title, first author, and year. Rank is not an input."""
    fields = []
    if pasted.get("title"):
        returned_title = returned.get("title")
        agrees = titles_agree(pasted.get("title"), returned_title) if returned_title else None
        fields.append(
            {"field": "title", "pasted": pasted.get("title"), "returned": returned_title, "agrees": agrees}
        )
    if pasted.get("author"):
        family = first_family(pasted.get("author"))
        returned_family = returned.get("first_author")
        if family and returned_family:
            agrees = family.casefold() == str(returned_family).casefold()
        else:
            agrees = None
        fields.append(
            {
                "field": "first_author",
                "pasted": family or pasted.get("author"),
                "returned": returned_family,
                "agrees": agrees,
            }
        )
    if pasted.get("year"):
        returned_year = returned.get("year")
        if returned_year is None or returned_year == "":
            agrees = None
        else:
            agrees = str(pasted.get("year")) == str(returned_year)
        fields.append(
            {
                "field": "year",
                "pasted": str(pasted.get("year")),
                "returned": None if returned_year is None else str(returned_year),
                "agrees": agrees,
            }
        )
    if not fields:
        verdict = "skipped"
    elif any(item["agrees"] is False for item in fields):
        verdict = "mismatch"
    elif any(item["agrees"] is None for item in fields):
        verdict = "insufficient"
    else:
        verdict = "match"
    return {"verdict": verdict, "fields": fields}


def status_payload(status: str, **extra) -> dict:
    body = {
        "ok": True,
        "status": status,
        "checked_before_retraction": True,
        "note": STATUS_NOTES.get(status, ""),
        "scope": SCOPE,
    }
    if status == "exists_no_integrity_source":
        body["writer_sentence"] = EXISTS_NO_INTEGRITY
        body["extract_empty_is_not_clean"] = True
    body.update(extra)
    return body


def assign_record_status(ref: dict, calls: list[dict]) -> dict:
    if ref.get("not_checkable") or (not ref.get("doi") and not ref.get("title")):
        return status_payload("not_checkable", raw=ref.get("raw") or "")
    doi = normalize_doi(ref.get("doi"))
    if doi:
        return _doi_status(ref, doi, calls)
    return _title_status(ref, calls)


def _doi_status(ref: dict, doi: str, calls: list[dict]) -> dict:
    csv = _find(calls, "rw_lookup_doi", "doi", doi) or {}
    agency = _find(calls, "doi_agency", "doi", doi)
    pasted = _pasted(ref)
    base = {"doi": doi, "extract_total": csv.get("total"), "pasted": pasted}
    if not agency or not agency.get("ok") or not agency.get("registration"):
        return status_payload("registration_unchecked", **base)
    registration = agency.get("registration")
    agency_view = _agency_view(agency)
    if registration == "not_registered":
        return status_payload("doi_not_registered", **base, agency=agency_view)
    if registration == "other":
        datacite = _find(calls, "datacite_work", "doi", doi) or {}
        returned = _from_datacite(datacite)
        comparison = compare_identity(pasted, returned) if returned else {"verdict": "skipped", "fields": []}
        extra = {
            **base,
            "agency": agency_view,
            "returned": returned,
            "comparison": comparison,
            "crossref_notices": "unavailable",
            "datacite_http_status": datacite.get("http_status"),
        }
        if comparison["verdict"] == "mismatch":
            return status_payload("identity_mismatch", **extra)
        if comparison["verdict"] == "match" and csv.get("total") == 0:
            return status_payload("exists_no_integrity_source", **extra)
        return status_payload("doi_other_agency", **extra)
    work = _find(calls, "crossref_doi", "doi", doi) or {}
    returned = {
        "title": work.get("title"),
        "first_author": work.get("first_author"),
        "year": work.get("year"),
    }
    comparison = compare_identity(pasted, returned)
    extra = {**base, "agency": agency_view, "returned": returned, "comparison": comparison}
    if comparison["verdict"] == "mismatch":
        return status_payload("identity_mismatch", **extra)
    return status_payload("registered_crossref", **extra, identity=comparison["verdict"])


def _title_status(ref: dict, calls: list[dict]) -> dict:
    title = ref.get("title") or ""
    csv = _find(calls, "rw_lookup_title", "title", title) or {}
    search = _find(calls, "crossref_title", "title", title) or {}
    candidates = search.get("candidates") or []
    top = candidates[0] if candidates else {}
    returned = {
        "title": top.get("title"),
        "first_author": top.get("first_author"),
        "year": top.get("year"),
        "doi": top.get("doi"),
    }
    pasted = _pasted(ref)
    comparison = compare_identity(pasted, returned)
    if csv.get("total") == 1:
        return status_payload(
            "extract_title_match",
            query=title,
            extract_total=1,
            record_ids=csv.get("record_ids"),
            comparison=comparison,
        )
    title_matched = titles_agree(title, top.get("title"))
    if comparison["verdict"] == "match":
        return status_payload(
            "registered_crossref",
            query=title,
            comparison=comparison,
            matched_doi=top.get("doi"),
            identity="match",
        )
    if comparison["verdict"] == "mismatch" and title_matched:
        return status_payload(
            "identity_mismatch",
            query=title,
            pasted=pasted,
            returned=returned,
            comparison=comparison,
        )
    return status_payload(
        "title_unverified",
        query=title,
        extract_total=csv.get("total"),
        accepted=False,
    )


def _pasted(ref: dict) -> dict:
    pasted = {}
    if ref.get("title"):
        pasted["title"] = ref["title"]
    if ref.get("author"):
        pasted["author"] = ref["author"]
    if ref.get("year"):
        pasted["year"] = str(ref["year"])
    return pasted


def _agency_view(agency: dict) -> dict:
    return {
        "registration": agency.get("registration"),
        "agency_id": agency.get("agency_id"),
        "agency_label": agency.get("agency_label"),
        "source": agency.get("source"),
        "crossref_http_status": agency.get("crossref_http_status"),
        "fallback_http_status": agency.get("fallback_http_status"),
        "registration_status": agency.get("registration_status"),
    }


def _from_datacite(payload: dict) -> dict:
    if not payload or not payload.get("ok"):
        return {}
    return {
        "title": payload.get("title"),
        "first_author": payload.get("first_author"),
        "year": payload.get("year"),
    }


def _find(calls: list[dict], name: str, key: str, value: str):
    norm = normalize_doi if key == "doi" else normalize_title
    wanted = norm(str(value))
    for call in calls:
        if call.get("name") != name:
            continue
        if norm(str((call.get("args") or {}).get(key) or "")) != wanted:
            continue
        try:
            return json.loads(call.get("result") or "")
        except json.JSONDecodeError:
            return None
    return None
