import json
import re
from pathlib import Path

from retraction_agent.catalog import get_catalog
from retraction_agent.identity import STATUS_NOTES
from retraction_agent.orchestrate import handle_turn
from retraction_agent.samples import INTEGRITY_SAMPLE, SAMPLE_1_TURN_1, SAMPLE_1_TURN_2, SAMPLE_2, SAMPLE_3
from retraction_agent.verdicts import (
    FOOTER,
    build_verdicts,
    labels_in,
    render_verdict_response,
    select_candidates,
    shares_half,
)
from tests.fakes import FakeCrossref, scripted_complete
from tests.test_orchestrate import _AgencyCrossref, _DataCite

ROOT = Path(__file__).resolve().parents[1]
BANNED = (
    "Do not ",
    "Say ",
    "Call it",
    "writer_sentence",
    "record_status",
    "rw_lookup",
    "crossref_doi",
)
STATUS_CODES = (
    "doi_not_registered",
    "doi_other_agency",
    "title_unverified",
    "identity_mismatch",
    "not_checkable",
    "exists_no_integrity_source",
    "registered_crossref",
    "extract_title_match",
    "registration_unchecked",
)
EXPECTED = [
    "DO NOT CITE",
    "DOESN'T CHECK OUT",
    "UNCONFIRMED",
    "DOESN'T CHECK OUT",
    "UNCONFIRMED",
    "UNCONFIRMED",
    "DO NOT CITE",
    "DO NOT CITE",
]


def _sample_four():
    return handle_turn(
        {"messages": []},
        INTEGRITY_SAMPLE,
        complete_fn=scripted_complete(
            "Snapshot fb5f174f. No record is a data limit. We check existence and integrity."
        ),
        catalog=get_catalog(),
        crossref=_AgencyCrossref(),
        datacite=_DataCite(),
    )


def test_sample_four_verdicts_follow_the_readme_order():
    response = _sample_four()["response"]
    assert labels_in(response) == EXPECTED
    assert response.startswith("Confirm which title you meant. The choices are listed under the table.")
    assert "3 do not cite, 2 doesn't check out, 3 unconfirmed." in response
    assert "| # | Verdict | What we found | What to do |" in response
    assert FOOTER not in response
    assert "Retraction Watch #70104." in response
    table_lines = [line for line in response.splitlines() if line.startswith("|")]
    assert table_lines
    assert all("snapshot" not in line.casefold() for line in table_lines)
    assert "concerns about data" in response
    assert "2026-02-25" in response
    assert "Highly accurate protein structure prediction with AlphaFold" in response
    assert "Jumper" in response and "2021" in response
    assert "DataCite has this paper. The Retraction Watch file does not cover this publisher" in response
    assert "withdrawal or retraction notice" in response
    assert "This paper exists" not in response
    assert "mistyped or invented" in response
    assert "this alone is not proof." in response
    assert "the retraction notice" in response
    assert "10.3390/nano10122325" in response
    assert "An expression of concern was recorded earlier, on 2024-09-27." in response
    assert "2026-07-24" in response
    assert "Retraction Watch #73988." in response
    assert "Query: Modeling Geometry and Semantics of Physical Damages" in response


def test_sample_two_is_one_row_in_the_same_format():
    result = handle_turn(
        {"messages": []},
        SAMPLE_2,
        complete_fn=scripted_complete("Snapshot fb5f174f. No record is a data limit."),
        catalog=get_catalog(),
        crossref=FakeCrossref(),
    )
    response = result["response"]
    assert labels_in(response) == ["NO ISSUES FOUND"]
    assert response.startswith("1 no issues found.")
    assert "does not mean the paper is sound." in response
    assert FOOTER in response
    assert "Snapshot fb5f174f" in response
    data = [line for line in response.splitlines() if "NO ISSUES FOUND" in line]
    assert data and "snapshot" not in data[0].casefold()


def test_a_do_not_cite_only_result_has_no_footer():
    response = render_verdict_response(
        [
            {
                "n": 1,
                "label": "DO NOT CITE",
                "reason": "Retraction on record",
                "found": "The retraction is dated 2026-02-25. Retraction Watch #70104.",
                "action": "Leave it out of your bibliography.",
            }
        ]
    )
    assert labels_in(response) == ["DO NOT CITE"]
    assert FOOTER not in response
    assert "No issues found never means" not in response


def test_final_responses_omit_instructions_and_tool_names():
    turns = [
        (_sample_four()["response"]),
        handle_turn(
            {"messages": []},
            SAMPLE_2,
            complete_fn=scripted_complete("Snapshot fb5f174f. No record is a data limit."),
            catalog=get_catalog(),
            crossref=FakeCrossref(),
        )["response"],
    ]
    session = {"messages": []}
    turns.append(
        handle_turn(
            session,
            SAMPLE_1_TURN_1,
            complete_fn=scripted_complete(),
            catalog=get_catalog(),
            crossref=FakeCrossref(),
        )["response"]
    )
    turns.append(
        handle_turn(
            session,
            SAMPLE_1_TURN_2,
            complete_fn=scripted_complete(),
            catalog=get_catalog(),
            crossref=FakeCrossref(),
        )["response"]
    )
    turns.append(
        handle_turn(
            {"messages": []},
            'In the shipped extract, how many notice rows does the journal "plos one" have?',
            complete_fn=scripted_complete("PLoS One has 1680 notice rows in snapshot fb5f174f. This is not a rate."),
            catalog=get_catalog(),
            crossref=FakeCrossref(),
        )["response"]
    )
    turns.append(
        handle_turn(
            {"messages": []},
            SAMPLE_3,
            complete_fn=scripted_complete("Hindawi has 11524 notice rows in snapshot fb5f174f. This is not a rate."),
            catalog=get_catalog(),
            crossref=FakeCrossref(),
        )["response"]
    )
    for response in turns:
        for piece in BANNED:
            assert piece not in response
        for code in STATUS_CODES:
            assert f"`{code}`" not in response


def test_status_notes_are_descriptions():
    blob = "\n".join(STATUS_NOTES.values())
    assert "Do not " not in blob
    assert "Say " not in blob
    assert "Call it" not in blob
    assert "following extract row of zero" not in STATUS_NOTES["registered_crossref"]
    assert "not proof" in STATUS_NOTES["doi_not_registered"]
    assert "could not be verified" in STATUS_NOTES["title_unverified"]


def test_title_candidates_need_half_their_words_and_stop_at_three():
    query = "Modeling Geometry and Semantics of Physical Damages"
    close = query + " and more words"
    far = "Quantum chromodynamics and lattice gauge theory"
    assert shares_half(query, close)
    assert not shares_half(query, far)
    candidates = [{"title": close, "doi": f"10.1000/c{index}"} for index in range(5)]
    candidates.append({"title": far, "doi": "10.1000/far"})
    picked = select_candidates(query, candidates)
    assert [item["doi"] for item in picked] == ["10.1000/c0", "10.1000/c1", "10.1000/c2"]


def test_filler_words_and_one_shared_word_do_not_make_a_similar_title():
    query = "Modeling Geometry and Semantics of Physical Damages"
    assert not shares_half(query, "The Semantics of Verbs")
    assert not shares_half(query, "What Is Semantics?")
    assert not shares_half(query, "Modeling Meanings in Robots and in the Semantic Web")
    assert shares_half(query, "Modeling Geometry and Semantics of Physical Damages using IFC")
    assert shares_half(query, "Geometry of Physical Damages")


def test_a_distant_title_is_not_offered_for_confirmation():
    class Far(FakeCrossref):
        def search_title(self, title):
            self.title_calls.append(title)
            return json.dumps(
                {
                    "ok": True,
                    "query": title,
                    "clear_match": False,
                    "candidates": [
                        {
                            "doi": "10.9999/other",
                            "title": "Quantum chromodynamics and lattice gauge theory",
                        }
                    ],
                }
            )

    result = handle_turn(
        {"messages": []},
        "Modeling Geometry and Semantics of Physical Damages",
        complete_fn=scripted_complete("Snapshot fb5f174f."),
        catalog=get_catalog(),
        crossref=Far(),
    )
    assert "Confirm which title you meant" not in result["response"]
    assert (
        "We didn't find a paper with a similar title to this one "
        "Modeling Geometry and Semantics of Physical Damages. "
        "Paste the full title, authors, and DOI, then run the check again."
    ) in result["response"]
    assert labels_in(result["response"]) == ["UNCONFIRMED"]


def test_a_crossref_retraction_update_is_a_verdict_without_an_extract_row():
    ref = {"doi": "10.1000/updated"}
    calls = [
        {
            "name": "record_status",
            "args": {"doi": ref["doi"]},
            "result": json.dumps({"status": "registered_crossref", "identity": "match", "extract_total": 0}),
        },
        {
            "name": "rw_lookup_doi",
            "args": {"doi": ref["doi"]},
            "result": json.dumps({"total": 0, "rows": [], "nature_counts": {}}),
        },
        {
            "name": "crossref_doi",
            "args": {"doi": ref["doi"]},
            "result": json.dumps(
                {
                    "ok": True,
                    "updated_by": [
                        {
                            "type": "retraction",
                            "source": "retraction-watch",
                            "date": "2024-01-02",
                            "record_id": "42",
                        }
                    ],
                    "update_to": [],
                }
            ),
        },
    ]
    verdict = build_verdicts([ref], calls, "fb5f174f")[0]
    assert verdict["label"] == "DO NOT CITE"
    assert "Retraction Watch #42." in verdict["found"]
    assert "snapshot" not in verdict["found"]

    calls[2]["result"] = json.dumps(
        {"ok": True, "updated_by": [{"type": "correction", "date": "2024-03-01"}], "update_to": []}
    )
    assert build_verdicts([ref], calls, "fb5f174f")[0]["label"] == "CHECK FIRST"

    calls[2]["result"] = json.dumps({"ok": True, "updated_by": [], "update_to": []})
    clear = build_verdicts([ref], calls, "fb5f174f")[0]
    assert clear["label"] == "NO ISSUES FOUND"
    assert clear["reason"] == "Record found, no notice"
    assert "does not mean the paper is sound." in clear["action"]
    assert "matches your citation" not in clear["found"]


def test_frontend_renders_a_table_and_hides_the_tool_log():
    html = (ROOT / "frontend" / "index.html").read_text()
    js = (ROOT / "frontend" / "app.js").read_text()
    css = (ROOT / "frontend" / "styles.css").read_text()
    assert "Show how the agents worked" in html
    assert 'class="work"' in html
    assert html.count("<details") == 1
    assert 'class="how"' not in html
    assert "<summary>How it works</summary>" not in html
    assert 'class="info-boxes"' in html
    for title in ("What it checks", "Who it is for", "How to use it"):
        assert title in html
    assert "Read as" in js
    assert "not found in your paste" in js
    assert "parsed_references" in js
    assert "cdn" not in html.casefold() and "unpkg" not in html.casefold()
    assert "escapeHtml" in js
    assert "textContent" in js
    assert "innerHTML" not in js.split("function renderAnswer")[1].split("function showTools")[0]
    for name in ("chip-red", "chip-amber", "chip-grey", "chip-blue"):
        assert name in js
        assert name in css
    assert "green" not in css.casefold()
    assert "not proof the paper is sound" in html
    assert 'id="send"' not in html
    assert ">Ask<" not in html
    assert "setTimeout(refreshPreview, 600)" in js
    assert 'addEventListener("paste"' in js
    assert "metaKey" in js
    assert "fallback: false" in js
    assert ".prepend(" in js
    for label in ("DOI link", "Reference with DOI", "Reading list (8)", "Publisher question"):
        assert label in js
    assert "Full citation" not in js
    assert "Article URL" not in js


def test_what_it_checks_keeps_only_the_verified_lines():
    html = (ROOT / "frontend" / "index.html").read_text()
    box = html.split("<h2>What it checks</h2>", 1)[1].split("</article>", 1)[0]
    for line in ("Does it exist?", "Was it retracted or corrected?", "How we read your paste"):
        assert line in box
    for phrase in (
        "doi.org",
        "DataCite",
        "exact title match",
        "first author and year must agree",
        "does not check out",
        "Retraction Watch",
        "update-to",
        "before Run check",
        "can only copy text you pasted",
        "UNCONFIRMED, not skipped",
    ):
        assert phrase in box
    assert "This paper exists" not in html
    assert "A registry has a record" in html


def test_a_clear_result_claims_a_match_only_when_it_was_tested():
    doi_only = build_verdicts(
        [{"doi": "10.1000/only-doi"}],
        [_status("10.1000/only-doi", {"status": "registered_crossref", "comparison": {"verdict": "skipped", "fields": []}})],
        "fb5f174f",
    )[0]
    assert doi_only["label"] == "NO ISSUES FOUND"
    assert doi_only["reason"] == "Record found, no notice"
    assert "You pasted only the DOI, so we could not compare the title." in doi_only["found"]
    assert "matches your citation" not in doi_only["found"]
    matched = build_verdicts(
        [{"doi": "10.1000/full", "title": "Deep learning", "author": "LeCun, Y.", "year": "2015"}],
        [
            _status(
                "10.1000/full",
                {
                    "status": "registered_crossref",
                    "agency": {"agency_label": "Crossref"},
                    "pasted": {"title": "Deep learning", "author": "LeCun, Y.", "year": "2015"},
                    "comparison": {"verdict": "match", "fields": [{"field": "title", "agrees": True}]},
                },
            )
        ],
        "fb5f174f",
    )[0]
    assert "Crossref has a record that matches your citation." in matched["found"]
    assert "title, authors and year" not in matched["found"]
    title_only = build_verdicts(
        [{"title": "Deep learning"}],
        [
            {
                "name": "record_status",
                "args": {"title": "Deep learning"},
                "result": json.dumps(
                    {
                        "status": "registered_crossref",
                        "pasted": {"title": "Deep learning"},
                        "comparison": {"verdict": "match", "fields": [{"field": "title", "agrees": True}]},
                    }
                ),
            }
        ],
        "fb5f174f",
    )[0]
    assert title_only["label"] == "NO ISSUES FOUND"
    assert "matches your citation" in title_only["found"]
    assert "title, authors and year" not in title_only["found"]
    other = build_verdicts(
        [{"doi": "10.48550/arxiv.1706.03762"}],
        [
            _status(
                "10.48550/arxiv.1706.03762",
                {
                    "status": "exists_no_integrity_source",
                    "agency": {"agency_label": "DataCite", "registration": "other"},
                },
            )
        ],
        "fb5f174f",
    )[0]
    assert other["label"] == "UNCONFIRMED"
    assert other["reason"] == "Exists, no retraction data"
    assert other["found"] == (
        "DataCite has this paper. The Retraction Watch file does not cover this publisher, "
        "so a retraction or correction could not be checked."
    )
    assert "This paper exists" not in other["found"]
    assert other["action"].startswith("Look it up on the arXiv or publisher page")


def _status(doi: str, payload: dict) -> dict:
    return {"name": "record_status", "args": {"doi": doi}, "result": json.dumps(payload)}


def test_each_reason_line_follows_the_status():
    def one(ref, status, calls=None):
        made = calls or [_status(ref.get("doi") or "", status)]
        if not calls and ref.get("title") and not ref.get("doi"):
            made = [{"name": "record_status", "args": {"title": ref["title"]}, "result": json.dumps(status)}]
        return build_verdicts([ref], made, "fb5f174f")[0]

    unread = one({"raw": "Smith (2012).", "unparsed": True}, {})
    assert unread["reason"] == "Could not read this citation"
    paper = one({"raw": "https://nytimes.com/story", "not_checkable": True}, {"status": "not_checkable"})
    assert paper["reason"] == "Not a paper"
    missing = one({"doi": "10.9999/missing"}, {"status": "doi_not_registered"})
    assert missing["reason"] == "DOI not found in any registry"
    assert missing["label"] == "DOESN'T CHECK OUT"
    mismatch = one(
        {"doi": "10.1000/other", "title": "Past title"},
        {"status": "identity_mismatch", "pasted": {"title": "Past title"}, "returned": {"title": "Other", "first_author": "Ada", "year": "2020"}},
    )
    assert mismatch["reason"] == "Link is a different paper"
    assert "different paper than the one you pasted" in mismatch["found"]
    live = one({"doi": "10.1000/down"}, {"status": "registration_unchecked"})
    assert live["reason"] == "Live check did not return"
    unmatched = one({"title": "No such paper title here"}, {"status": "title_unverified", "query": "No such paper title here"})
    assert unmatched["reason"] == "No matching record found"
    assert unmatched["found"] == "This title did not match one paper."
    assert unmatched["action"] == (
        "We didn't find a paper with a similar title to this one No such paper title here. "
        "Paste the full title, authors, and DOI, then run the check again."
    )
    close_query = "Modeling Geometry and Semantics of Physical Damages"
    close = build_verdicts(
        [{"title": close_query}],
        [
            {
                "name": "record_status",
                "args": {"title": close_query},
                "result": json.dumps({"status": "title_unverified", "query": close_query}),
            },
            {
                "name": "crossref_title",
                "args": {"title": close_query},
                "result": json.dumps(
                    {"candidates": [{"title": close_query + " using IFC", "doi": "10.1000/ifc"}]}
                ),
            },
        ],
        "fb5f174f",
    )[0]
    assert close["found"] == "This title did not match one paper."
    assert close["action"] == "Confirm which title you meant. The choices are listed under the table."
    js = (ROOT / "frontend" / "app.js").read_text()
    block = js.split("const SEVERITY", 1)[1].split("};", 1)[0]
    ranks = [block.index(label) for label in ("DO NOT CITE", "DOESN'T CHECK OUT", "CHECK FIRST", "UNCONFIRMED", "NO ISSUES FOUND")]
    assert ranks == sorted(ranks)


def test_legend_covers_every_headline_and_hides_the_old_ones():
    from retraction_agent.verdicts import ORDER, prose_notes

    html = (ROOT / "frontend" / "index.html").read_text()
    js = (ROOT / "frontend" / "app.js").read_text()
    for label in ORDER:
        assert label in html
    retired = (
        "WRONG LINK",
        "WRONG KIND OF LINK",
        "NOT FOUND",
        "COULD NOT VERIFY",
        "FOUND CAN'T CHECK RETRACTIONS",
        "NOT A PAPER",
        "NO NOTICE FOUND",
    )
    for label in retired:
        assert label not in html
        assert label not in js
    scaffold = "```markdown | Step | Result | Details | | :--- | :--- | :--- |"
    assert prose_notes(scaffold) == ""
    assert "Step | Result | Details" not in prose_notes("A real note. " + scaffold)
