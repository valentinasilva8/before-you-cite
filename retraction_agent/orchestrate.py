"""Lead, parallel researchers, one gap round, then the writer. Extract lookups finish before Crossref."""

import json
from concurrent.futures import ThreadPoolExecutor

from retraction_agent.citations import (
    confirmation_question,
    enforce_citations,
    grounded_fallback,
)
from retraction_agent.config import limits
from retraction_agent.identity import assign_record_status, compare_identity
from retraction_agent.extract import apply_llm_fallback, fallback_complete
from retraction_agent.llm import complete as default_complete
from retraction_agent.llm import run_agent
from retraction_agent.normalize import normalize_doi, normalize_title
from retraction_agent.planning import (
    AUDIT_PROMPT,
    CROSSREF_PROMPT,
    DEFAULT_ASK,
    LEAD_PROMPT,
    PATTERN_PROMPT,
    PATTERN_WRITER_PROMPT,
    WRITER_PROMPT,
    chunk,
    finalize_plan,
)
from retraction_agent.verdicts import (
    build_verdicts,
    prose_notes,
    render_verdict_response,
    select_candidates,
)
from retraction_agent.tools import (
    AUDIT_TOOLS,
    CROSSREF_TOOLS,
    LEAD_TOOLS,
    PATTERN_TOOLS,
    audit_runner,
    crossref_runner,
    lead_runner,
    pattern_runner,
)


def handle_turn(session: dict, message: str, *, complete_fn=None, catalog=None, crossref=None, datacite=None) -> dict:
    """Run one user turn. Researchers each get a fresh message list and their own tool loop."""
    from retraction_agent.catalog import get_catalog
    from retraction_agent.crossref import get_client
    from retraction_agent.datacite import get_datacite

    catalog = catalog or get_catalog()
    crossref = crossref or get_client()
    datacite = datacite or get_datacite()
    complete_fn = complete_fn or default_complete
    message = (message or "").strip()
    session.setdefault("messages", [])
    session.setdefault("pending_titles", [])
    session.setdefault("corpus", [])
    if not message:
        response = DEFAULT_ASK
        session["messages"].append({"role": "assistant", "content": response})
        return {"response": response, "tool_calls": []}

    session["messages"].append({"role": "user", "content": message[:20000]})
    tool_calls: list[dict] = []
    try:
        plan, lead_calls = _lead(session, message, complete_fn)
        tool_calls.extend(lead_calls)
        if plan["action"] == "ask":
            response = plan.get("ask") or DEFAULT_ASK
            session["messages"].append({"role": "assistant", "content": response})
            session["pack_summary"] = ""
            return {"response": response, "tool_calls": tool_calls}

        tool_calls.extend(
            _research(plan, catalog, crossref, datacite, complete_fn, session, message)
        )
        pending = _pending(tool_calls, catalog)
        session["pending_titles"] = pending
        fresh = [call["result"] for call in tool_calls if call["agent"] != "lead"]
        session["corpus"].extend(fresh)
        references = plan.get("references") or []
        notes_only = bool(references)
        draft = _writer(message, tool_calls, pending, catalog, complete_fn, notes_only=notes_only)

        def regenerate(previous: str, problems: list[str]) -> str:
            return _writer(
                message,
                tool_calls,
                pending,
                catalog,
                complete_fn,
                previous,
                problems,
                notes_only=notes_only,
            )

        checked = enforce_citations(draft, session["corpus"], catalog.commit, pending, regenerate)
        if references:
            verdicts = build_verdicts(references, tool_calls, catalog.commit_short)
            response = render_verdict_response(verdicts)
            notes = prose_notes(checked, limit=3)
            if notes:
                response = response + "\n\n" + notes
        else:
            response = prose_notes(checked, limit=None)
            if not response:
                response = prose_notes(grounded_fallback(tool_calls, catalog.commit_short), limit=None)
        if pending:
            question = confirmation_question(pending)
            if question.casefold() not in response.casefold():
                response = (response + "\n\n" + question).strip()
        session["messages"].append({"role": "assistant", "content": response})
        session["pack_summary"] = _summary(tool_calls, pending)
        return {"response": response, "tool_calls": tool_calls}
    except Exception as exc:
        response = f"Model call failed: {type(exc).__name__}: {str(exc)[:300]}"
        session["messages"].append({"role": "assistant", "content": response})
        return {"response": response, "tool_calls": tool_calls}


def _lead(session: dict, message: str, complete_fn) -> tuple[dict, list[dict]]:
    transcript = session.get("messages") or []
    prior = [item for item in transcript[:-1] if item.get("role") in {"user", "assistant"}][-4:]
    user = {
        "question": message[:20000],
        "prior_turns": prior,
        "pack_summary": session.get("pack_summary") or "",
        "pending_titles": session.get("pending_titles") or [],
    }
    messages = [
        {"role": "system", "content": LEAD_PROMPT},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]
    text, calls = run_agent(
        messages,
        LEAD_TOOLS,
        lead_runner(),
        "lead",
        limits()["lead_tool_rounds"],
        complete_fn,
    )
    model_plan = None
    for call in calls:
        if call["name"] == "submit_plan":
            model_plan = call["args"]
    if model_plan is None and text and not _has_work(message, session):
        model_plan = {"action": "ask", "ask": text.strip()}
    plan = finalize_plan(message, model_plan, session.get("pending_titles") or [])
    extractor = fallback_complete if complete_fn is default_complete else complete_fn
    calls.extend(apply_llm_fallback(message, plan, extractor))
    public = {
        key: plan[key]
        for key in ("action", "ask", "references", "journals", "publishers", "top_publishers", "limit", "planned_by")
    }
    recorded = False
    for call in calls:
        if call["name"] == "submit_plan":
            call["args"] = public
            call["result"] = json.dumps({"accepted": True, "planned_by": plan["planned_by"]})
            recorded = True
    if not recorded:
        calls.append(
            {
                "agent": "lead",
                "name": "submit_plan",
                "args": public,
                "result": json.dumps({"accepted": True, "planned_by": plan["planned_by"]}),
            }
        )
    return plan, calls


def _has_work(message: str, session: dict) -> bool:
    from retraction_agent.planning import parse_references, wants_top_publishers

    if parse_references(message) or wants_top_publishers(message):
        return True
    return bool(session.get("pending_titles")) and message.casefold().startswith(("yes", "confirm"))


def _research(plan, catalog, crossref, datacite, complete_fn, session, message) -> list[dict]:
    cap = limits()
    calls: list[dict] = []
    jobs = []
    references = plan["references"]
    chunks = chunk(references, cap["audit_chunk_size"]) if references else []
    for index, group in enumerate(chunks, start=1):
        jobs.append(("audit", index, group))
    if plan["journals"] or plan["publishers"] or plan["top_publishers"]:
        jobs.append(("pattern", None, plan))

    if jobs:
        with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
            futures = [
                (kind, index, pool.submit(_one_job, kind, index, payload, catalog, complete_fn))
                for kind, index, payload in jobs
            ]
            for kind, index, future in futures:
                calls.extend(future.result())

    calls.extend(_casefold_round(calls, catalog))
    if not session.get("crossref_down"):
        cross_calls = _crossref_after_csv(plan, calls, crossref, datacite, complete_fn, catalog)
        calls.extend(cross_calls)
        if _source_failed(cross_calls):
            session["crossref_down"] = True
    elif _dois_and_titles(plan, calls) != ([], []):
        calls.append(
            {
                "agent": "crossref-researcher",
                "name": "crossref_doi",
                "args": {},
                "result": json.dumps(
                    {
                        "ok": False,
                        "error": "skipped",
                        "detail": "Crossref timed out or returned 429 earlier in this session, so it was not called again.",
                        "snapshot": catalog.commit,
                        "snapshot_short": catalog.commit_short,
                    }
                ),
            }
        )
    calls.extend(_record_statuses(plan.get("references") or [], calls))
    return calls


def _one_job(kind, index, payload, catalog, complete_fn) -> list[dict]:
    if kind == "audit":
        return _audit(index, payload, catalog, complete_fn)
    return _pattern(payload, catalog, complete_fn)


def _audit(index: int, references: list[dict], catalog, complete_fn) -> list[dict]:
    agent = f"audit-researcher-{index}"
    task = {"research_round": 1, "references": references}
    messages = [
        {"role": "system", "content": AUDIT_PROMPT.format(agent=agent)},
        {"role": "user", "content": json.dumps(task, ensure_ascii=False)},
    ]
    _, calls = run_agent(messages, AUDIT_TOOLS, audit_runner(catalog), agent, limits()["max_tool_rounds"], complete_fn)
    _ensure_audit(agent, references, calls, catalog)
    return calls


def _pattern(plan: dict, catalog, complete_fn) -> list[dict]:
    task = {
        "research_round": 1,
        "journals": plan.get("journals") or [],
        "publishers": plan.get("publishers") or [],
        "top_publishers": bool(plan.get("top_publishers")),
        "limit": plan.get("limit") or limits()["top_publishers"],
    }
    messages = [
        {"role": "system", "content": PATTERN_PROMPT},
        {"role": "user", "content": json.dumps(task, ensure_ascii=False)},
    ]
    _, calls = run_agent(
        messages, PATTERN_TOOLS, pattern_runner(catalog), "pattern-researcher", limits()["max_tool_rounds"], complete_fn
    )
    _ensure_pattern("pattern-researcher", task, calls, catalog)
    return calls


def _casefold_round(calls: list[dict], catalog) -> list[dict]:
    """Second research round: one exact string when casefold matches exactly one value in the file."""
    extra = []
    seen = set()
    for call in calls:
        if call["name"] != "rw_pattern":
            continue
        try:
            data = json.loads(call["result"])
        except json.JSONDecodeError:
            continue
        unique = data.get("casefold_unique")
        field = data.get("field")
        if not unique or data.get("rows"):
            continue
        key = (field, unique)
        if key in seen:
            continue
        seen.add(key)
        args = {"journal": unique} if field == "journal" else {"publisher": unique}
        result = pattern_runner(catalog)("rw_pattern", args)
        extra.append(
            {
                "agent": "pattern-researcher",
                "name": "rw_pattern",
                "args": {**args, "research_round": 2},
                "result": result,
            }
        )
    return extra


def _crossref_after_csv(plan, calls, crossref, datacite, complete_fn, catalog) -> list[dict]:
    dois, titles = _dois_and_titles(plan, calls)
    if not dois and not titles:
        return []
    task = {"dois": dois, "titles": titles}
    messages = [
        {"role": "system", "content": CROSSREF_PROMPT},
        {"role": "user", "content": json.dumps(task, ensure_ascii=False)},
    ]
    _, made = run_agent(
        messages,
        CROSSREF_TOOLS,
        crossref_runner(crossref, datacite),
        "crossref-researcher",
        limits()["max_tool_rounds"],
        complete_fn,
    )
    title_meta = {}
    for ref in plan.get("references") or []:
        if ref.get("title") and not ref.get("doi"):
            title_meta[normalize_title(ref["title"])] = ref
    _ensure_crossref(dois, titles, made, crossref, datacite, catalog, calls, title_meta)
    return made


def _dois_and_titles(plan, calls) -> tuple[list[str], list[str]]:
    dois = []
    titles = []
    seen_dois = set()
    seen_titles = set()
    for ref in plan.get("references") or []:
        doi = normalize_doi(ref.get("doi"))
        title = ref.get("title")
        if doi and doi not in seen_dois:
            seen_dois.add(doi)
            dois.append(doi)
        elif title:
            key = normalize_title(title)
            if key not in seen_titles:
                seen_titles.add(key)
                titles.append(title)
    for doi in _dois_from_exact_titles(calls):
        if doi not in seen_dois:
            seen_dois.add(doi)
            dois.append(doi)
    return dois, titles


def _dois_from_exact_titles(calls: list[dict]) -> list[str]:
    """One DOI already on a single exact title row is in hand. Unclear Crossref candidates are not."""
    found = []
    for call in calls:
        if call["name"] != "rw_lookup_title":
            continue
        try:
            data = json.loads(call["result"])
        except json.JSONDecodeError:
            continue
        rows = data.get("rows") or []
        if data.get("total") != 1 or len(rows) != 1:
            continue
        row = rows[0]
        doi = normalize_doi(row.get("original_doi")) or normalize_doi(row.get("retraction_doi"))
        if doi:
            found.append(doi)
    return found


def _ensure_audit(agent: str, references: list[dict], calls: list[dict], catalog) -> None:
    runner = audit_runner(catalog)
    for ref in references:
        doi = ref.get("doi")
        title = ref.get("title")
        if doi and not _called(calls, "rw_lookup_doi", doi=doi):
            args = {"doi": doi}
            calls.append(_harness_call(agent, "rw_lookup_doi", args, runner("rw_lookup_doi", args)))
        elif title and not doi and not _called(calls, "rw_lookup_title", title=title):
            args = {"title": title}
            calls.append(_harness_call(agent, "rw_lookup_title", args, runner("rw_lookup_title", args)))


def _ensure_pattern(agent: str, task: dict, calls: list[dict], catalog) -> None:
    runner = pattern_runner(catalog)
    for journal in task["journals"]:
        if not _called(calls, "rw_pattern", journal=journal):
            args = {"journal": journal}
            calls.append(_harness_call(agent, "rw_pattern", args, runner("rw_pattern", args)))
    for publisher in task["publishers"]:
        if not _called(calls, "rw_pattern", publisher=publisher):
            args = {"publisher": publisher}
            calls.append(_harness_call(agent, "rw_pattern", args, runner("rw_pattern", args)))
    if task["top_publishers"] and not any(call["name"] == "rw_top_publishers" for call in calls):
        args = {"limit": int(task["limit"])}
        calls.append(_harness_call(agent, "rw_top_publishers", args, runner("rw_top_publishers", args)))


def _ensure_crossref(dois, titles, calls, crossref, datacite, catalog, prior, title_meta=None) -> None:
    runner = crossref_runner(crossref, datacite)
    for doi in dois:
        if _source_failed(calls):
            break
        if not _doi_in_audit(prior + calls, doi):
            looked = audit_runner(catalog)("rw_lookup_doi", {"doi": doi})
            calls.append(
                _harness_call("audit-researcher-1", "rw_lookup_doi", {"doi": doi, "after_title_match": True}, looked)
            )
        if not _called(prior + calls, "doi_agency", doi=doi):
            result = runner("doi_agency", {"doi": doi})
            calls.append(_harness_call("crossref-researcher", "doi_agency", {"doi": doi}, result))
            if _failed(result):
                break
        registration = _registration(prior + calls, doi)
        if registration == "crossref" and not _called(prior + calls, "crossref_doi", doi=doi):
            result = runner("crossref_doi", {"doi": doi})
            calls.append(_harness_call("crossref-researcher", "crossref_doi", {"doi": doi}, result))
            if _failed(result):
                break
        elif registration == "other" and datacite is not None and not _called(prior + calls, "datacite_work", doi=doi):
            result = datacite.get_work(doi)
            calls.append(_harness_call("crossref-researcher", "datacite_work", {"doi": doi}, result))
            if _failed(result):
                break
    if _source_failed(calls):
        return
    for title in titles:
        if _called(calls, "crossref_title", title=title):
            continue
        args = {"title": title}
        result = runner("crossref_title", args)
        calls.append(_harness_call("crossref-researcher", "crossref_title", args, result))
        if _failed(result):
            break
    _follow_clear_titles(calls, crossref, datacite, catalog, prior, title_meta or {})


def _follow_clear_titles(calls, crossref, datacite, catalog, prior, title_meta=None) -> None:
    """A title hit is followed only when title, first author, and year agree. Rank is not enough."""
    runner = crossref_runner(crossref, datacite)
    for call in list(calls):
        if call["name"] != "crossref_title":
            continue
        try:
            data = json.loads(call["result"])
        except json.JSONDecodeError:
            continue
        candidates = data.get("candidates") or []
        if not data.get("ok") or not candidates:
            continue
        top = candidates[0]
        query = data.get("query") or call["args"].get("title")
        meta = (title_meta or {}).get(normalize_title(query)) or {}
        comparison = compare_identity(
            {"title": meta.get("title") or query, "author": meta.get("author"), "year": meta.get("year")},
            {"title": top.get("title"), "first_author": top.get("first_author"), "year": top.get("year")},
        )
        if comparison["verdict"] != "match":
            continue
        doi = normalize_doi(top.get("doi"))
        if not doi or _called(prior + calls, "crossref_doi", doi=doi) or _called(prior + calls, "datacite_work", doi=doi):
            continue
        if _source_failed(calls):
            break
        if not _doi_in_audit(prior + calls, doi):
            looked = audit_runner(catalog)("rw_lookup_doi", {"doi": doi})
            calls.append(
                _harness_call("audit-researcher-1", "rw_lookup_doi", {"doi": doi, "after_clear_title": True}, looked)
            )
        if not _called(prior + calls, "doi_agency", doi=doi):
            agency_result = runner("doi_agency", {"doi": doi})
            calls.append(_harness_call("crossref-researcher", "doi_agency", {"doi": doi}, agency_result))
            if _failed(agency_result):
                break
        if _registration(prior + calls, doi) != "crossref":
            if _registration(prior + calls, doi) == "other" and datacite is not None:
                result = datacite.get_work(doi)
                calls.append(_harness_call("crossref-researcher", "datacite_work", {"doi": doi}, result))
                if _failed(result):
                    break
            continue
        result = runner("crossref_doi", {"doi": doi})
        calls.append(_harness_call("crossref-researcher", "crossref_doi", {"doi": doi}, result))
        if _failed(result):
            break


def _doi_in_audit(calls, doi: str) -> bool:
    for call in calls:
        if call["name"] == "rw_lookup_doi" and normalize_doi(call["args"].get("doi")) == normalize_doi(doi):
            return True
    return False


def _called(calls, name: str, **expected) -> bool:
    for call in calls:
        if call["name"] != name:
            continue
        args = call["args"]
        matched = True
        for key, value in expected.items():
            if key in {"doi"}:
                if normalize_doi(str(args.get(key) or "")) != normalize_doi(str(value)):
                    matched = False
            elif key in {"title", "journal", "publisher", "author"}:
                if normalize_title(str(args.get(key) or "")) != normalize_title(str(value)):
                    matched = False
            elif args.get(key) != value:
                matched = False
        if matched:
            return True
    return False


def _failed(result: str) -> bool:
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return False
    return data.get("error") in {"timeout", "429"}


def _source_failed(calls: list[dict]) -> bool:
    return any(_is_agent(call["agent"], "crossref-researcher") and _failed(call["result"]) for call in calls)


def _harness_agent(agent: str) -> str:
    suffix = " (harness)"
    if agent.endswith(suffix):
        return agent
    return agent + suffix


def _harness_call(agent: str, name: str, args: dict, result: str) -> dict:
    return {"agent": _harness_agent(agent), "name": name, "args": args, "result": result}


def _is_agent(agent: str, name: str) -> bool:
    return agent == name or agent == _harness_agent(name)


def _pending(calls: list[dict], catalog) -> list[dict]:
    pending = []
    for call in calls:
        if call["name"] != "record_status":
            continue
        try:
            data = json.loads(call["result"])
        except json.JSONDecodeError:
            continue
        if data.get("status") != "title_unverified":
            continue
        query = data.get("query") or call["args"].get("title")
        candidates = []
        for other in calls:
            if other["name"] != "crossref_title":
                continue
            if normalize_title(other["args"].get("title")) != normalize_title(query):
                continue
            try:
                candidates = json.loads(other["result"]).get("candidates") or []
            except json.JSONDecodeError:
                candidates = []
        close = select_candidates(query, candidates)
        if close:
            pending.append({"query": query, "candidates": close})
    return pending


def _record_statuses(references: list[dict], calls: list[dict]) -> list[dict]:
    made = []
    for ref in references:
        payload = assign_record_status(ref, calls)
        args = {}
        if ref.get("doi"):
            args["doi"] = ref["doi"]
        elif ref.get("title"):
            args["title"] = ref["title"]
        else:
            args["raw"] = ref.get("raw") or ""
        if ref.get("parsed_by"):
            args["parsed_by"] = ref["parsed_by"]
        made.append(
            {
                "agent": _agent_for(calls, ref),
                "name": "record_status",
                "args": args,
                "result": json.dumps(payload, ensure_ascii=False),
            }
        )
    return made


def _agent_for(calls: list[dict], ref: dict) -> str:
    doi = ref.get("doi")
    title = ref.get("title")
    for call in calls:
        if doi and call["name"] == "rw_lookup_doi" and normalize_doi(call["args"].get("doi")) == normalize_doi(doi):
            return call["agent"]
        if (
            title
            and not doi
            and call["name"] == "rw_lookup_title"
            and normalize_title(call["args"].get("title")) == normalize_title(title)
        ):
            return call["agent"]
    return "audit-researcher-1"


def _registration(calls: list[dict], doi: str) -> str | None:
    for call in calls:
        if call["name"] != "doi_agency" or normalize_doi(call["args"].get("doi")) != normalize_doi(doi):
            continue
        try:
            return json.loads(call["result"]).get("registration")
        except json.JSONDecodeError:
            return None
    return None


def _writer(
    message, tool_calls, pending, catalog, complete_fn, previous=None, problems=None, notes_only=False
) -> str:
    evidence = [
        {"agent": call["agent"], "name": call["name"], "args": call["args"], "result": call["result"]}
        for call in tool_calls
        if call["agent"] != "lead"
    ]
    payload = {
        "question": message,
        "snapshot": catalog.commit,
        "snapshot_short": catalog.commit_short,
        "committed_at": catalog.manifest.get("committed_at"),
        "tool_results": evidence,
        "unconfirmed_titles": pending,
    }
    if previous is not None:
        payload["previous_draft"] = previous
        payload["fix"] = (
            "Rewrite. Remove every record id, DOI, and commit that is not in the tool results. "
            "Remove any claim that an unconfirmed title was retracted. "
            "A paper with no record is not fine, reliable, or unretracted. "
            f"Problems: {problems}"
        )
    prompt = WRITER_PROMPT if notes_only else PATTERN_WRITER_PROMPT
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    text, calls = run_agent(messages, None, lambda name, args: "{}", "writer", 1, complete_fn)
    if calls:
        raise RuntimeError("writer returned tool calls")
    return text


def _summary(tool_calls: list[dict], pending: list[dict]) -> str:
    bits = []
    for call in tool_calls:
        if call["agent"] == "lead":
            continue
        try:
            data = json.loads(call["result"])
        except json.JSONDecodeError:
            continue
        if call["name"] == "rw_lookup_doi":
            bits.append(f"doi {data.get('query_doi')} rows {data.get('total')}")
        elif call["name"] == "rw_lookup_title":
            bits.append(f"title rows {data.get('total')}")
        elif call["name"] == "rw_pattern":
            bits.append(f"pattern {data.get('matched')} rows {data.get('rows')} casefold {data.get('casefold_unique')}")
        elif call["name"] == "rw_top_publishers":
            bits.append(f"top publishers {len(data.get('publishers') or [])}")
        elif call["name"] == "crossref_doi":
            bits.append(f"crossref doi {data.get('doi') or data.get('error')}")
        elif call["name"] == "crossref_title":
            bits.append(f"crossref title clear {data.get('clear_match')}")
    if pending:
        bits.append("pending title confirmation")
    return "; ".join(bits)[:2000]

