import json

import re

from retraction_agent.catalog import get_catalog
from retraction_agent.orchestrate import _format_top_publishers, handle_turn
from retraction_agent.identity import EXISTS_NO_INTEGRITY
from retraction_agent.planning import parse_references
from retraction_agent.samples import INTEGRITY_SAMPLE, SAMPLE_1_TURN_1, SAMPLE_1_TURN_2, SAMPLE_3
from tests.fakes import DRAFT, FakeCrossref, Reply, ToolCall, TracingCatalog, scripted_complete


def test_bibliography_is_csv_then_crossref_and_strips_guesses():
    events = []
    catalog = TracingCatalog(get_catalog(), events)
    crossref = FakeCrossref(events=events)
    session = {"messages": []}
    first = handle_turn(
        session,
        SAMPLE_1_TURN_1,
        complete_fn=scripted_complete(),
        catalog=catalog,
        crossref=crossref,
    )
    assert events.index("crossref") > events.index("csv")
    assert "csv" not in events[events.index("crossref") :]
    assert "99999999" not in first["response"]
    assert "10.1234/notreal" not in first["response"]
    assert "the paper is fine" not in first["response"].casefold()
    assert "70548" not in first["response"]
    assert "70104" in first["response"]
    assert first["response"].startswith("Confirm which title you meant. The choices are listed under the table.")
    names = [call["name"] for call in first["tool_calls"]]
    assert names.index("rw_lookup_doi") < names.index("crossref_doi")
    assert "crossref_title" in names
    assert any(call["agent"] == "audit-researcher-1 (harness)" for call in first["tool_calls"])
    assert all(isinstance(call["result"], str) for call in first["tool_calls"])
    assert all(set(call) == {"agent", "name", "args", "result"} for call in first["tool_calls"])

    second = handle_turn(
        session,
        SAMPLE_1_TURN_2,
        complete_fn=scripted_complete(),
        catalog=catalog,
        crossref=crossref,
    )
    assert "70548" in second["response"]
    assert "70104" in second["response"]
    assert session["corpus"]
    assert any(call["name"] == "rw_lookup_title" and "using IFC" in call["args"].get("title", "") for call in second["tool_calls"])


def test_writer_is_called_without_tools():
    complete = scripted_complete("Record 70104 in snapshot fb5f174f is a Retraction for DOI 10.3390/nano10122325.")
    handle_turn(
        {"messages": []},
        "1. 10.3390/nano10122325",
        complete_fn=complete,
        catalog=get_catalog(),
        crossref=FakeCrossref(),
    )
    assert complete.state["writer_tools"]
    assert all(tools is None for tools in complete.state["writer_tools"])


def test_a_person_name_alone_is_not_looked_up():
    def complete(messages, tools):
        if messages[0]["content"].startswith("You are the lead"):
            return Reply("", [ToolCall("submit_plan", {"action": "dispatch", "references": [{"author": "Ayman M Atta"}]})])
        raise AssertionError("researchers should not run")

    result = handle_turn(
        {"messages": []},
        "Check Ayman M Atta",
        complete_fn=complete,
        catalog=get_catalog(),
        crossref=FakeCrossref(),
    )
    text = result["response"]
    assert "Names are not unique, so I will not look people up by name." in text
    assert "DOI" in text and "title" in text and "journal" in text and "publisher" in text
    assert not any(
        call["name"].startswith("rw_") or call["name"].startswith("crossref") or call["name"] in {"doi_agency", "datacite_work"}
        for call in result["tool_calls"]
    )


def test_a_skipped_lookup_is_labeled_harness():
    def complete(messages, tools):
        system = messages[0]["content"]
        if system.startswith("You are the lead"):
            return Reply("", [ToolCall("submit_plan", {"action": "dispatch", "references": []})])
        if system.startswith("You are audit-researcher-1") and not any(item.get("role") == "tool" for item in messages):
            return Reply("", [ToolCall("rw_lookup_doi", {"doi": "10.1000/kept"})])
        if system.startswith("You are the writer"):
            return Reply("Snapshot fb5f174f. No record is a data limit.")
        return Reply("done")

    result = handle_turn(
        {"messages": []},
        "1. 10.1000/kept\n2. 10.1000/skipped",
        complete_fn=complete,
        catalog=get_catalog(),
        crossref=FakeCrossref(),
    )
    lookups = [call for call in result["tool_calls"] if call["name"] == "rw_lookup_doi"]
    by_doi = {call["args"]["doi"]: call for call in lookups}
    assert by_doi["10.1000/kept"]["agent"] == "audit-researcher-1"
    assert by_doi["10.1000/skipped"]["agent"] == "audit-researcher-1 (harness)"
    assert set(by_doi["10.1000/skipped"]) == {"agent", "name", "args", "result"}
    assert isinstance(by_doi["10.1000/skipped"]["result"], str)


def test_vague_topic_asks_and_does_not_research():
    def complete(messages, tools):
        if messages[0]["content"].startswith("You are the lead"):
            return Reply("Which paper, author, journal, or publisher should I check?")
        raise AssertionError("researchers should not run")

    result = handle_turn(
        {"messages": []},
        "Has the work on CRISPR been retracted?",
        complete_fn=complete,
        catalog=get_catalog(),
        crossref=FakeCrossref(),
    )
    assert "Which paper" in result["response"]
    assert not any(call["name"].startswith("rw_") or call["name"].startswith("crossref_") for call in result["tool_calls"])


def test_casefold_journal_is_the_second_research_round():
    crossref = FakeCrossref()
    result = handle_turn(
        {"messages": []},
        'In the shipped extract, how many notice rows does the journal "plos one" have? Do not compute a rate.',
        complete_fn=scripted_complete("PLoS One has 1680 notice rows in snapshot fb5f174f. This is not a rate."),
        catalog=get_catalog(),
        crossref=crossref,
    )
    pattern_calls = [call for call in result["tool_calls"] if call["name"] == "rw_pattern"]
    assert json.loads(pattern_calls[0]["result"])["rows"] == 0
    assert json.loads(pattern_calls[1]["result"])["rows"] == 1680
    assert pattern_calls[1]["args"]["research_round"] == 2
    assert crossref.work_calls == []
    assert "1680" in result["response"]


def test_top_publishers_are_not_a_crossref_call():
    crossref = FakeCrossref()
    result = handle_turn(
        {"messages": []},
        SAMPLE_3,
        complete_fn=scripted_complete("Hindawi has 11524 notice rows in snapshot fb5f174f. This is not a rate."),
        catalog=get_catalog(),
        crossref=crossref,
    )
    top = [call for call in result["tool_calls"] if call["name"] == "rw_top_publishers"]
    assert top
    body = json.loads(top[0]["result"])
    assert body["publishers"][0]["publisher"] == "Hindawi"
    assert body["publishers"][0]["notice_rows"] == 11524
    assert body["not_a_rate"] is True
    assert crossref.work_calls == []
    assert crossref.title_calls == []


def test_twenty_five_references_make_five_audit_researchers():
    lines = [f"{index}. 10.1000/item{index}" for index in range(1, 31)]
    crossref = FakeCrossref()
    result = handle_turn(
        {"messages": []},
        "Audit this bibliography.\n" + "\n".join(lines),
        complete_fn=scripted_complete("No record in snapshot fb5f174f for these DOIs. No record is a data limit."),
        catalog=get_catalog(),
        crossref=crossref,
    )
    lookups = [call for call in result["tool_calls"] if call["name"] == "rw_lookup_doi"]
    assert len(lookups) == 25
    agents = {call["agent"] for call in lookups}
    assert agents == {f"audit-researcher-{index} (harness)" for index in range(1, 6)}
    assert len(crossref.work_calls) == 25


def test_crossref_timeout_is_not_repeated_in_the_session():
    crossref = FakeCrossref(error="timeout")
    session = {"messages": []}
    handle_turn(
        session,
        "1. 10.3390/nano10122325",
        complete_fn=scripted_complete("No record is a data limit in snapshot fb5f174f."),
        catalog=get_catalog(),
        crossref=crossref,
    )
    assert len(crossref.work_calls) == 1
    handle_turn(
        session,
        "1. 10.1038/s41586-021-03819-2",
        complete_fn=scripted_complete("No record is a data limit in snapshot fb5f174f."),
        catalog=get_catalog(),
        crossref=crossref,
    )
    assert len(crossref.work_calls) == 1
    assert session.get("crossref_down") is True


class _AgencyCrossref(FakeCrossref):
    def doi_agency(self, doi):
        self.agency_calls.append(doi)
        lowered = doi.casefold()
        if "not-a-real" in lowered or "10.9999/" in lowered:
            return json.dumps(
                {
                    "ok": True,
                    "doi": doi,
                    "registration": "not_registered",
                    "source": "doi.org",
                    "crossref_http_status": 404,
                    "crossref_body": "Resource not found.",
                    "fallback_http_status": 200,
                    "registration_status": "DOI does not exist",
                }
            )
        if "48550" in lowered:
            return json.dumps(
                {
                    "ok": True,
                    "doi": doi,
                    "registration": "other",
                    "agency_id": "datacite",
                    "agency_label": "DataCite",
                    "source": "crossref",
                    "crossref_http_status": 200,
                }
            )
        return super().doi_agency(doi)

    def get_work(self, doi):
        self.work_calls.append(doi)
        lowered = doi.casefold()
        if "nano10122325" in lowered:
            title = (
                "RETRACTED: Magnetic Ionic Liquid Nanocatalyst to Improve Mechanical "
                "and Thermal Properties of Epoxy Nanocomposites"
            )
            first, year = "Atta", 2020
        elif "s41586-021-03819-2" in lowered:
            title = "Highly accurate protein structure prediction with AlphaFold"
            first, year = "Jumper", 2021
        else:
            return super().get_work(doi)
        return json.dumps(
            {"ok": True, "doi": doi, "title": title, "first_author": first, "year": year, "updated_by": [], "update_to": []}
        )


class _DataCite:
    def __init__(self, title="Attention Is All You Need", first="Vaswani", year=2017):
        self.calls = []
        self.title = title
        self.first = first
        self.year = year

    def get_work(self, doi):
        self.calls.append(doi)
        return json.dumps(
            {
                "ok": True,
                "doi": doi,
                "http_status": 200,
                "title": self.title,
                "first_author": self.first,
                "year": self.year,
                "rate_limit_headers": {},
                "rate_limit_headers_present": False,
            }
        )


def _statuses(result):
    found = {}
    for call in result["tool_calls"]:
        if call["name"] != "record_status":
            continue
        body = json.loads(call["result"])
        found[call["args"].get("doi") or call["args"].get("title") or call["args"].get("raw")] = body
    return found


def test_eight_citations_are_classified_before_retraction_wording():
    parsed = parse_references(INTEGRITY_SAMPLE)
    assert len(parsed) == 8
    crossref = _AgencyCrossref()
    datacite = _DataCite()
    result = handle_turn(
        {"messages": []},
        INTEGRITY_SAMPLE,
        complete_fn=scripted_complete(
            "Snapshot fb5f174f. No record is a data limit. We check existence and integrity."
        ),
        catalog=get_catalog(),
        crossref=crossref,
        datacite=datacite,
    )
    statuses = _statuses(result)
    nano = statuses["10.3390/nano10122325"]
    assert nano["status"] == "registered_crossref"
    assert nano["checked_before_retraction"] is True
    assert nano["identity"] == "match"
    assert nano["extract_total"] == 1
    mismatch = statuses["10.1038/s41586-021-03819-2"]
    assert mismatch["status"] == "identity_mismatch"
    assert mismatch["pasted"]["title"].startswith("Magnetic Ionic Liquid")
    assert mismatch["returned"]["title"].startswith("Highly accurate protein")
    assert mismatch["returned"]["first_author"] == "Jumper"
    assert mismatch["returned"]["year"] == 2021
    arxiv = statuses["10.48550/arxiv.1706.03762"]
    assert arxiv["status"] == "exists_no_integrity_source"
    assert arxiv["writer_sentence"] == EXISTS_NO_INTEGRITY
    assert arxiv["extract_total"] == 0
    assert arxiv["extract_empty_is_not_clean"] is True
    assert arxiv["crossref_notices"] == "unavailable"
    fake = statuses["10.9999/not-a-real-work-before-you-cite"]
    assert fake["status"] == "doi_not_registered"
    assert fake["agency"]["crossref_http_status"] == 404
    assert "not proof" in fake["note"]
    short = [body for key, body in statuses.items() if body["status"] == "title_unverified"]
    assert len(short) == 1
    assert "could not be verified" in short[0]["note"]
    assert "fabricat" not in short[0]["note"].casefold()
    assert any(body["status"] == "not_checkable" for body in statuses.values())
    assert statuses["10.3390/nano16050293"]["extract_total"] == 1
    assert statuses["10.1039/d1ra07974c"]["extract_total"] == 2
    assert all("48550" not in doi and "not-a-real" not in doi for doi in crossref.work_calls)
    assert datacite.calls
    names = [call["name"] for call in result["tool_calls"]]
    assert names.index("rw_lookup_doi") < names.index("doi_agency") < names.index("crossref_doi")
    assert names.index("record_status") > names.index("rw_lookup_doi")


def test_a_resolved_arxiv_id_that_is_a_different_paper_is_a_mismatch():
    crossref = _AgencyCrossref()
    datacite = _DataCite(title="Attention Is All You Need", first="Vaswani", year=2017)
    message = (
        "Other, Person, et al. Not The Attention Paper At All. 1999. "
        "https://doi.org/10.48550/arXiv.9999.99999"
    )
    result = handle_turn(
        {"messages": []},
        message,
        complete_fn=scripted_complete("Snapshot fb5f174f. Both sides are reported."),
        catalog=get_catalog(),
        crossref=crossref,
        datacite=datacite,
    )
    body = json.loads([call for call in result["tool_calls"] if call["name"] == "record_status"][0]["result"])
    assert body["status"] == "identity_mismatch"
    assert body["returned"]["title"] == "Attention Is All You Need"
    assert crossref.work_calls == []


def _publisher_blocks(text: str) -> list[str]:
    parts = text.split("\n\n")
    assert parts[0].startswith("Top ")
    assert parts[-1].startswith("A reason token is counted once per row")
    return parts[1:-1]


def _parsed_block(block: str) -> dict:
    lines = block.split("\n")
    assert len(lines) <= 3
    assert len(lines) == 3
    head = re.fullmatch(r"(.+): ([\d,]+) notice rows", lines[0])
    assert head
    tokens = []
    body = lines[1].removeprefix("  Reason tokens (rows): ")
    assert body != lines[1]
    for piece in body.split(", "):
        match = re.fullmatch(r"(.+) \((\d+)\)", piece)
        assert match
        tokens.append({"token": match.group(1), "rows": int(match.group(2))})
    dates = []
    date_body = lines[2].removeprefix("  Batch-like dates (rows): ")
    assert date_body != lines[2]
    for piece in date_body.split(", "):
        match = re.fullmatch(r"(\d{1,2}/\d{1,2}/\d{4})(?: \((\d+)\))?", piece)
        assert match
        item = {"date": match.group(1)}
        if match.group(2) is not None:
            item["notice_rows"] = int(match.group(2))
        dates.append(item)
    return {
        "publisher": head.group(1),
        "notice_rows": int(head.group(2).replace(",", "")),
        "reason_tokens": tokens,
        "batch_dates": dates,
    }


def test_publisher_question_is_one_block_per_publisher():
    complete = scripted_complete("The writer must not invent these counts.")
    result = handle_turn(
        {"messages": []},
        SAMPLE_3,
        complete_fn=complete,
        catalog=get_catalog(),
        crossref=FakeCrossref(),
    )
    assert complete.state["writer_tools"] == []
    text = result["response"]
    assert "The writer must not invent these counts." not in text
    top = get_catalog().top_publishers(8)
    blocks = _publisher_blocks(text)
    assert len(blocks) == 8
    parsed = [_parsed_block(block) for block in blocks]
    assert [item["publisher"] for item in parsed] == [item["publisher"] for item in top["publishers"]]
    for got, expected in zip(parsed, top["publishers"]):
        assert got["notice_rows"] == expected["notice_rows"]
        assert got["reason_tokens"] == expected["reason_tokens"]
        shown_dates = [(item["date"], item.get("notice_rows")) for item in got["batch_dates"]]
        tool_dates = []
        for item in expected["batch_dates"]:
            date = str(item["date"]).split()[0]
            tool_dates.append((date, item.get("notice_rows")))
        assert shown_dates == tool_dates
    assert "Hindawi: 11,524 notice rows" in text
    assert "PLoS: 1,805 notice rows" in text
    assert text.startswith(
        f"Top 8 publishers by notice rows in Retraction Watch snapshot {top['snapshot_short']}."
    )
    assert set(result) == {"response", "tool_calls"}
    for call in result["tool_calls"]:
        assert set(call) == {"agent", "name", "args", "result"}
        assert isinstance(call["result"], str)


def test_a_named_journal_keeps_the_writer_under_the_publisher_blocks():
    draft = "PLoS One has 1680 notice rows in snapshot fb5f174f. This is not a rate."
    complete = scripted_complete(draft)
    result = handle_turn(
        {"messages": []},
        'Which publishers have the most notice rows? Also, how many notice rows does the journal "PLoS One" have?',
        complete_fn=complete,
        catalog=get_catalog(),
        crossref=FakeCrossref(),
    )
    assert complete.state["writer_tools"]
    text = result["response"]
    assert text.index("Hindawi: 11,524 notice rows") < text.index(draft)
    assert text.index("separate entries.") < text.index(draft)


def test_a_batch_date_without_a_count_is_left_bare():
    text = _format_top_publishers(
        {
            "snapshot_short": "fb5f174f",
            "publishers": [
                {
                    "publisher": "Example",
                    "notice_rows": 12,
                    "reason_tokens": [{"token": "Paper Mill", "rows": 3}],
                    "batch_dates": [
                        {"date": "1/2/2024 0:00", "iso": "2024-01-02"},
                        {"date": "3/4/2020 0:00", "iso": "2020-03-04", "notice_rows": 4},
                    ],
                }
            ],
        }
    )
    assert "Example: 12 notice rows" in text
    assert "1/2/2024" in text
    assert "1/2/2024 (" not in text
    assert "3/4/2020 (4)" in text


def test_model_failure_is_not_replaced_with_a_written_answer():
    def complete(messages, tools):
        raise RuntimeError("vertex credentials missing")

    result = handle_turn(
        {"messages": []},
        "1. 10.3390/nano10122325",
        complete_fn=complete,
        catalog=get_catalog(),
        crossref=FakeCrossref(),
    )
    assert result["response"].startswith("Model call failed:")
    assert "70104" not in result["response"]
