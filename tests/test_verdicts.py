import json
from pathlib import Path

from retraction_agent.catalog import get_catalog
from retraction_agent.identity import STATUS_NOTES
from retraction_agent.orchestrate import handle_turn
from retraction_agent.samples import INTEGRITY_SAMPLE, SAMPLE_1_TURN_1, SAMPLE_1_TURN_2, SAMPLE_2, SAMPLE_3
from retraction_agent.verdicts import (
    FOOTER,
    build_verdicts,
    labels_in,
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
    "WRONG LINK",
    "FOUND CAN'T CHECK RETRACTIONS",
    "NOT FOUND",
    "COULD NOT VERIFY",
    "NOT A PAPER",
    "WRONG KIND OF LINK",
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
    assert response.startswith(
        "2 do not cite, 4 need fixing or verifying, 1 no notice found or can't check, 1 not a paper."
    )
    assert "| # | Verdict | What we found | What to do |" in response
    assert FOOTER in response
    assert "Retraction Watch #70104." in response
    table_lines = [line for line in response.splitlines() if line.startswith("|")]
    assert table_lines
    assert all("snapshot" not in line.casefold() for line in table_lines)
    assert "concerns about data" in response
    assert "2026-02-25" in response
    assert "Highly accurate protein structure prediction with AlphaFold" in response
    assert "Jumper" in response and "2021" in response
    assert "integrity was not checked" in response
    assert "mistyped or invented" in response
    assert "It is not proof." in response
    assert "The link is the retraction notice." in response
    assert "10.3390/nano10122325" in response
    assert "An expression of concern was recorded earlier, on 2024-09-27." in response
    assert "2026-07-24" in response
    assert "Retraction Watch #73988." in response
    assert "Confirm which work" in response


def test_sample_two_is_one_row_in_the_same_format():
    result = handle_turn(
        {"messages": []},
        SAMPLE_2,
        complete_fn=scripted_complete("Snapshot fb5f174f. No record is a data limit."),
        catalog=get_catalog(),
        crossref=FakeCrossref(),
    )
    response = result["response"]
    assert labels_in(response) == ["NO NOTICE FOUND"]
    assert response.startswith(
        "0 do not cite, 0 need fixing or verifying, 1 no notice found or can't check, 0 not a paper."
    )
    assert "not a guarantee of quality." in response
    assert FOOTER in response
    assert "Snapshot fb5f174f" in response
    data = [line for line in response.splitlines() if "NO NOTICE FOUND" in line]
    assert data and "snapshot" not in data[0].casefold()


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
    assert "Confirm which work" not in result["response"]
    assert "No close match found. Paste the full title, authors, and DOI." in result["response"]
    assert labels_in(result["response"]) == ["COULD NOT VERIFY"]


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
    assert clear["label"] == "NO NOTICE FOUND"
    assert "not a guarantee of quality." in clear["action"]


def test_frontend_renders_a_table_and_hides_the_tool_log():
    html = (ROOT / "frontend" / "index.html").read_text()
    js = (ROOT / "frontend" / "app.js").read_text()
    css = (ROOT / "frontend" / "styles.css").read_text()
    assert "Show how the agents worked" in html
    assert "<details" in html
    assert "cdn" not in html.casefold() and "unpkg" not in html.casefold()
    assert "escapeHtml" in js
    assert "textContent" in js
    assert "innerHTML" not in js.split("function renderAnswer")[1].split("function showTools")[0]
    for name in ("chip-red", "chip-amber", "chip-grey", "chip-blue"):
        assert name in js
        assert name in css
    assert "green" not in css.casefold()
    assert "not a clean bill of health" in html
