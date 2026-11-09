import json

from retraction_agent.catalog import get_catalog
from retraction_agent.orchestrate import handle_turn
from retraction_agent.reading import TITLE_MATCH_NOTE
from tests.fakes import FakeCrossref, scripted_complete


class _TitleMatchCrossref(FakeCrossref):
    def search_title(self, title):
        self.title_calls.append(title)
        return json.dumps(
            {
                "ok": True,
                "query": title,
                "clear_match": True,
                "candidates": [
                    {
                        "doi": "10.1000/title-match-only",
                        "title": title,
                        "first_author": "Shu",
                        "year": 2012,
                    }
                ],
            }
        )


def _entry(result):
    calls = [call for call in result["tool_calls"] if call["name"] == "parsed_references"]
    assert len(calls) == 1
    call = calls[0]
    assert call["agent"] == "(harness)"
    assert set(call) == {"agent", "name", "args", "result"}
    assert isinstance(call["result"], str)
    items = json.loads(call["result"])
    assert isinstance(items, list)
    return items


def _table_rows(response):
    rows = []
    for line in response.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or not cells[0].isdigit():
            continue
        rows.append(cells)
    return rows


def test_parsed_references_match_verdict_rows_in_order():
    message = "\n".join(
        [
            "https://doi.org/10.3390/nano10122325",
            "https://doi.org/10.9999/not-a-real-work",
            "1. Smith (2012).",
        ]
    )
    result = handle_turn(
        {"messages": []},
        message,
        complete_fn=scripted_complete(),
        catalog=get_catalog(),
        crossref=FakeCrossref(),
    )
    items = _entry(result)
    rows = _table_rows(result["response"])
    assert len(items) == len(rows)
    assert [item["doi"] for item in items] == [
        "10.3390/nano10122325",
        "10.9999/not-a-real-work",
        "",
    ]
    assert items[0]["parsed_by"] == "rules"
    assert items[1]["parsed_by"] == "rules"
    assert items[2]["parsed_by"] == "unreadable"
    assert items[2]["raw"].endswith("Smith (2012).")
    assert rows[2][1].startswith("UNCONFIRMED")
    assert "Could not read this citation" in rows[2][1]
    assert "parsed_references" not in result["response"]


def test_title_match_doi_carries_the_note():
    message = (
        "Shu, L. (2012). A completely invented title about coastal sediment transport. "
        "Journal of Fixtures."
    )
    result = handle_turn(
        {"messages": []},
        message,
        complete_fn=scripted_complete(),
        catalog=get_catalog(),
        crossref=_TitleMatchCrossref(),
    )
    items = _entry(result)
    rows = _table_rows(result["response"])
    assert len(items) == len(rows) == 1
    assert items[0]["parsed_by"] == "rules"
    assert items[0]["title"] == "A completely invented title about coastal sediment transport"
    assert items[0]["authors"] == "Shu, L."
    assert items[0]["year"] == "2012"
    assert items[0]["doi"] == "10.1000/title-match-only"
    assert TITLE_MATCH_NOTE in items[0]["notes"]
    assert "10.1000/title-match-only" not in message
