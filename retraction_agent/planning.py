"""Lead plan, bibliography parsing, and the prompts for each fresh context."""

import re

from retraction_agent.config import limits
from retraction_agent.normalize import arxiv_doi_from_text, normalize_doi, normalize_title

_DOI = re.compile(
    r"(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?(10\.\d{4,9}/[^\s,;<>\"')\]]+)",
    re.IGNORECASE,
)
_QUOTED = re.compile(r'"([^"]{2,200})"')
_YES = re.compile(
    r"^\s*(yes|yep|yeah|confirm|use (the )?first|use (the )?second|that one|the first|the second)\b",
    re.IGNORECASE,
)
_SKIP_PREFIXES = (
    "audit ",
    "has ",
    "which ",
    "what ",
    "in the ",
    "use the ",
    "use this ",
    "do not ",
    "don't ",
    "for the ",
    "compare ",
    "on the ",
    "yes",
    "confirm",
    "against ",
    "please ",
    "paste ",
    "check ",
    "show ",
    "list ",
    "how ",
    "why ",
    "when ",
    "where ",
    "who ",
)

DEFAULT_ASK = (
    "Which paper, journal, or publisher should I check? "
    "A topic alone is not enough to search this extract. "
    "Paste a DOI, a bibliography of up to 25 references, "
    "or the journal or publisher string from the extract. I will not pick a paper for you. "
    "Paste the full citation as it was written: title, authors, and link, not the link alone."
)

NAME_ONLY_ASK = (
    "Names are not unique, so I will not look people up by name. "
    "Paste a DOI, a title, a journal, or a publisher."
)

LEAD_PROMPT = """You are the lead for Before You Cite. You do not answer from memory. You do not see researcher scratchpads.

Call submit_plan exactly once.
- action "ask" when the user names no DOI, title, journal, or publisher. A topic such as CRISPR is this case. A person's name alone is also this case. Names are not unique, so do not look people up by name. Ask for a DOI, a title, a journal, or a publisher. Ask one question. Do not pick a paper. Do not search subject strings.
- action "dispatch" when they name a DOI, a title, a journal, a publisher, or ask for the publishers with the most notice rows.
- Put each DOI or title in references. Copy the pasted title, first author, and year onto a DOI reference. Do not invent a DOI for a title. Do not send a person as someone to look up.
- Journal and publisher strings go in journals or publishers exactly as typed. Do not rewrite PLOS ONE as PLoS One and do not rewrite The Lancet as Lancet.
- top_publishers true when they want publishers ranked by notice rows, reason tokens, or batch dates. That is not a rate.
- Never dispatch a guess for an unconfirmed title. If a previous turn is waiting on confirmation and the user confirms, put the confirmed DOI or the exact title they typed into references.
- At most 25 references. You do not call Crossref or the extract yourself. The harness checks the extract first, then Crossref.
"""

AUDIT_PROMPT = """You are {agent}, one audit researcher. Your message list is only this task. You do not see the user chat or any other researcher.

Call rw_lookup_doi once for each DOI and rw_lookup_title once for each title that has no DOI. Do not look people up by name.
Use the strings in the task. Do not call Crossref. Do not add facts from memory.
After the tools return, stop. One short sentence is enough.
"""

PATTERN_PROMPT = """You are the pattern researcher. You count notice rows in the frozen extract. You do not see the user chat.

Call rw_pattern once for each journal string and once for each publisher string, using the exact string in the task.
If top_publishers is true, call rw_top_publishers with limit 8.
Do not compute a rate. Do not call Crossref. Do not correct a journal string.
After the tools return, stop.
"""

CROSSREF_PROMPT = """You are the crossref researcher. You do not see the user chat or the extract rows except the identifiers in this task.

For each DOI, call doi_agency once. If registration is crossref, call crossref_doi once. If registration is other, call datacite_work once and do not call crossref_doi. If registration is not_registered, call neither.
Call crossref_title once per title that has no DOI. Do not accept the closest-ranked hit. Compare title, first author, and year with the pasted citation.
Do not call a tool twice for the same string. Do not request or quote an abstract.
After the tools return, stop.
"""

WRITER_PROMPT = """You are the writer. You have no tools. You see the question and the tool results, not the rest of the chat.

Write only from the tool results. Every sentence that states a status, date, reason, count, ISSN, or publisher cites the field, the record id or the DOI, and the snapshot commit copied from the tool results.
Read record_status before you write anything about retraction. The status is checked before the retraction result.
- doi_not_registered: no agency has this DOI. Call it a signal to check by hand. Do not call it proof.
- doi_other_agency: the DOI exists and is not Crossref. Do not treat that as suspicious. Say Crossref notices are unavailable. Still cite the extract total. An empty total is not clean.
- title_unverified: say the citation could not be verified. Do not call the citation invented.
- identity_mismatch: put the pasted title, first author, and year beside the returned title, first author, and year. Do not apply the resolved paper's retraction to the pasted citation.
- not_checkable: say it was not checked.
- exists_no_integrity_source: copy writer_sentence exactly. Then say the empty extract row is not clean.
- registered_crossref with extract total 0: no record is a data limit. Never say safe.
Reason text is the token list. Do not paraphrase a token into fraud or honest error.
If a DOI has total 0 and Crossref has no updated-by and no update-to, say there is no record in the extract for that DOI and that Crossref returned no update. Stop there for that DOI. No record is a data limit. Do not say the paper is reliable, peer-reviewed, fine, safe, safe to cite, or that it has not been retracted.
We check existence and integrity. We do not check whether the paper supports a claim made about it.
If Crossref failed, say the live check did not return, so a publisher-only update would not have been seen.
When several rows match, list every nature. Do not drop an earlier record.
A has-review relation is a review, not a notice. A RETRACTED: title prefix is not a reason.
Prefer the retraction-watch updated-by date and record-id. Do not cite a publisher updated-by date as the notice date.
If the CSV publisher string and the Crossref publisher string differ, cite both. Do not repair the file.
Cluster and publisher sentences use the counts in the tool results. Do not say a publisher or journal is the worst. Do not divide into a rate.
If a title has clear_match false and the extract title lookup total is 0, ask the user to confirm. Do not cite that candidate's status, record id, or DOI as the user's paper.
If a field is not in the tool results, leave it out.
"""


def chunk(items: list, size: int) -> list[list]:
    size = max(1, size)
    return [items[index : index + size] for index in range(0, len(items), size)]


def parse_references(message: str) -> list[dict]:
    """Pull citations out of a bibliography, keeping the pasted title, author, and year beside a DOI."""
    refs: list[dict] = []
    seen = set()
    lines = [line.strip() for line in (message or "").splitlines() if line.strip()]
    if not lines and (message or "").strip():
        lines = [(message or "").strip()]
    for line in lines:
        for ref in _citation_line(line):
            key = ref.get("doi") or normalize_title(ref.get("title") or "") or ref.get("raw")
            if not key or key in seen:
                continue
            seen.add(key)
            refs.append(ref)
    if not any(ref.get("doi") for ref in refs):
        for match in _DOI.finditer(message or ""):
            norm = normalize_doi(match.group(1))
            if norm and norm not in seen:
                seen.add(norm)
                refs.append({"doi": norm})
    return refs


def _citation_line(line: str) -> list[dict]:
    cleaned = re.sub(r"^\d+[\).\]]\s*", "", line).strip(" -*")
    if not cleaned:
        return []
    dois = []
    for match in _DOI.finditer(cleaned):
        norm = normalize_doi(match.group(1))
        if norm and norm not in dois:
            dois.append(norm)
    arxiv = arxiv_doi_from_text(cleaned)
    if arxiv and arxiv not in dois:
        dois.append(arxiv)
    if not dois and (cleaned.endswith("?") or cleaned.casefold().startswith(_SKIP_PREFIXES)):
        return []
    if cleaned.endswith("?"):
        author = None
        year = None
        title = None
    else:
        author = _author_of(cleaned)
        year = _year_of(cleaned)
        title = _title_of(cleaned, author)
    urls = re.findall(r"https?://[^\s)>\]]+", cleaned)
    other_urls = [url for url in urls if "doi.org" not in url.casefold() and "arxiv.org" not in url.casefold()]
    if dois:
        refs = []
        for index, doi in enumerate(dois):
            ref = {"doi": doi}
            if index == 0:
                if title:
                    ref["title"] = title
                if author:
                    ref["author"] = author
                if year:
                    ref["year"] = year
            refs.append(ref)
        return refs
    if title and len(title) >= 25:
        ref = {"title": title}
        if author:
            ref["author"] = author
        if year:
            ref["year"] = year
        return [ref]
    if other_urls:
        return [{"not_checkable": True, "raw": cleaned[:300]}]
    return []


def _author_of(line: str) -> str | None:
    match = re.match(r"^(.+?\bet al\.?)", line, re.IGNORECASE)
    if not match:
        return None
    author = " ".join(match.group(1).split())
    if len(author) > 160:
        return None
    return author


def _year_of(line: str) -> str | None:
    scrubbed = _DOI.sub(" ", line)
    scrubbed = re.sub(r"10\.48550/\S+", " ", scrubbed, flags=re.IGNORECASE)
    years = re.findall(r"\b(?:19|20)\d{2}\b", scrubbed)
    return years[-1] if years else None


def _title_of(line: str, author: str | None) -> str | None:
    text = line
    if author:
        found = text.casefold().find(author.casefold())
        if found >= 0:
            text = text[found + len(author) :]
    text = re.sub(r"https?://\S+", " ", text)
    text = _DOI.sub(" ", text)
    text = text.strip(" .;,-")
    sentence = re.split(r"\.\s+", text, maxsplit=1)[0]
    sentence = re.sub(r"\b(?:19|20)\d{2}\b", " ", sentence)
    sentence = " ".join(sentence.split()).strip(" .;,-")
    if len(sentence) < 12:
        return None
    return sentence


def quoted_strings(message: str) -> list[str]:
    return [match.strip() for match in _QUOTED.findall(message or "") if match.strip()]


def names_only_a_person(message: str) -> bool:
    """True when the message names a person and no DOI, title, journal, or publisher."""
    if parse_references(message) or wants_top_publishers(message):
        return False
    lowered = (message or "").casefold()
    if quoted_strings(message) and ("journal" in lowered or "publisher" in lowered):
        return False
    tokens = re.findall(r"\b[A-Z][a-zA-Z'\-]{1,}\b", message or "")
    names = [token for token in tokens if token.casefold() not in _NAME_WORDS]
    if len(names) >= 2:
        return True
    return len(names) == 1 and bool(re.match(r"^\s*(please\s+)?(check|look up|audit|search)\b", lowered))


_NAME_WORDS = {
    "has",
    "the",
    "work",
    "on",
    "been",
    "retracted",
    "check",
    "look",
    "up",
    "please",
    "audit",
    "this",
    "paper",
    "journal",
    "publisher",
    "title",
    "about",
    "what",
    "which",
    "show",
    "list",
}


def wants_top_publishers(message: str) -> bool:
    lowered = (message or "").casefold()
    if "publisher" not in lowered:
        return False
    return any(word in lowered for word in ("top", "most", "batch", "notice row", "notice rows"))


def apply_confirmation(message: str, pending: list[dict]) -> list[dict]:
    """Turn a bare yes into the confirmed candidate. A new title or DOI in the message wins instead."""
    if parse_references(message) or not pending or not _YES.search(message or ""):
        return []
    which = 0
    lowered = message.casefold()
    if re.search(r"\b(second|2)\b", lowered):
        which = 1
    added = []
    for item in pending:
        candidates = item.get("candidates") or []
        if _YES.search(message) and len(candidates) > 1 and not re.search(r"\b(first|second|1|2)\b", lowered):
            continue
        if which >= len(candidates):
            continue
        doi = normalize_doi(candidates[which].get("doi"))
        if doi:
            added.append({"doi": doi, "confirmed": True})
    return added


def finalize_plan(message: str, model_plan: dict | None, pending: list[dict]) -> dict:
    """Union the lead's plan with DOIs and titles detected in the message. Cap at 25."""
    detected = parse_references(message)
    if not detected:
        detected = apply_confirmation(message, pending)
    plan = _blank_plan()
    if model_plan:
        plan["action"] = model_plan.get("action") or "ask"
        plan["ask"] = (model_plan.get("ask") or "").strip()
        plan["journals"] = _strings(model_plan.get("journals"))
        plan["publishers"] = _strings(model_plan.get("publishers"))
        plan["top_publishers"] = bool(model_plan.get("top_publishers"))
        plan["limit"] = model_plan.get("limit") or limits()["top_publishers"]
        plan["references"] = _clean_refs(model_plan.get("references") or [])
        plan["planned_by"] = "lead"
    else:
        plan["planned_by"] = "harness"
        plan["ask"] = DEFAULT_ASK
    plan["references"] = _merge_refs(detected, plan["references"])
    lowered = (message or "").casefold()
    if "journal" in lowered:
        for name in quoted_strings(message):
            if name not in plan["journals"]:
                plan["journals"].append(name)
    elif "publisher" in lowered and not wants_top_publishers(message):
        for name in quoted_strings(message):
            if name not in plan["publishers"]:
                plan["publishers"].append(name)
    if wants_top_publishers(message):
        plan["top_publishers"] = True
    plan["references"] = [
        ref for ref in plan["references"] if ref.get("doi") or ref.get("title") or ref.get("not_checkable")
    ]
    has_work = bool(plan["references"] or plan["journals"] or plan["publishers"] or plan["top_publishers"])
    if names_only_a_person(message) and not has_work:
        plan["action"] = "ask"
        plan["ask"] = NAME_ONLY_ASK
        return plan
    if has_work:
        plan["action"] = "dispatch"
    elif plan["action"] != "ask":
        plan["action"] = "ask"
    if plan["action"] == "ask" and not plan["ask"]:
        plan["ask"] = DEFAULT_ASK
    cap = limits()["max_references"]
    if len(plan["references"]) > cap:
        plan["references"] = plan["references"][:cap]
        plan["references_truncated"] = True
    else:
        plan["references_truncated"] = False
    return plan


def _blank_plan() -> dict:
    return {
        "action": "ask",
        "ask": "",
        "references": [],
        "journals": [],
        "publishers": [],
        "top_publishers": False,
        "limit": limits()["top_publishers"],
        "planned_by": "harness",
        "references_truncated": False,
    }


def _strings(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _clean_refs(refs: list) -> list[dict]:
    cleaned = []
    for item in refs:
        if not isinstance(item, dict):
            continue
        ref = {}
        doi = normalize_doi(item.get("doi"))
        title = " ".join(str(item.get("title") or "").split())
        author = " ".join(str(item.get("author") or "").split())
        year = str(item.get("year") or "").strip()
        if item.get("not_checkable"):
            cleaned.append({"not_checkable": True, "raw": str(item.get("raw") or "")[:300]})
            continue
        if doi:
            ref["doi"] = doi
        if title:
            ref["title"] = title
        if author and (doi or title):
            ref["author"] = author
        if year and (doi or title):
            ref["year"] = year
        if ref:
            cleaned.append(ref)
    return cleaned


def _merge_refs(primary: list[dict], secondary: list[dict]) -> list[dict]:
    merged = []
    dois = set()
    titles = set()
    raws = set()
    for ref in list(primary) + list(secondary):
        if ref.get("not_checkable"):
            raw = ref.get("raw") or ""
            if raw in raws:
                continue
            raws.add(raw)
            merged.append({"not_checkable": True, "raw": raw})
            continue
        doi = ref.get("doi")
        title = ref.get("title")
        author = ref.get("author")
        year = ref.get("year")
        if doi:
            if doi in dois:
                continue
            dois.add(doi)
            item = {"doi": doi}
            if title:
                item["title"] = title
            if author:
                item["author"] = author
            if year:
                item["year"] = str(year)
            if ref.get("confirmed"):
                item["confirmed"] = True
            merged.append(item)
            continue
        if title:
            key = normalize_title(title)
            if key in titles:
                continue
            titles.add(key)
            item = {"title": title}
            if author:
                item["author"] = author
            if year:
                item["year"] = str(year)
            merged.append(item)
            continue
    return merged
