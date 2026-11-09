"""Labelled rows checked against the frozen extract and the existing fakes."""

import json
from pathlib import Path

import pytest

from retraction_agent.orchestrate import handle_turn
from retraction_agent.verdicts import labels_in
from tests.fakes import Reply, ToolCall, scripted_complete
from tests.test_orchestrate import _AgencyCrossref, _DataCite

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests" / "regression_set.json").read_text(encoding="utf-8"))["cases"]


def _table_rows(response: str) -> list[str]:
    rows = []
    for line in response.splitlines():
        if not line.startswith("|"):
            continue
        cells = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in {"#", ""} or set(cells[0]) <= {"-", ":"}:
            continue
        rows.append(line)
    return rows


class _ShuCrossref(_AgencyCrossref):
    def get_work(self, doi):
        if "10.1073/pnas.1209746109" in doi.casefold():
            return json.dumps(
                {
                    "ok": True,
                    "doi": doi,
                    "title": (
                        "Signing at the beginning makes ethics salient and decreases "
                        "dishonest self-reports in comparison to signing at the end"
                    ),
                    "first_author": "Shu",
                    "year": 2012,
                    "updated_by": [],
                    "update_to": [],
                }
            )
        return super().get_work(doi)


def _complete_for(case):
    items = case.get("llm_items")
    if items is None:
        return scripted_complete("Snapshot fb5f174f.")

    def complete(messages, tools):
        system = messages[0]["content"]
        if system.startswith("You are the lead"):
            return Reply("", [ToolCall("submit_plan", {"action": "dispatch", "references": []})])
        if system.startswith("You extract"):
            if any(item.get("role") == "tool" for item in messages):
                return Reply("done")
            return Reply("", [ToolCall("submit_extractions", {"items": items})])
        if system.startswith("You are the writer"):
            return Reply("Snapshot fb5f174f.")
        return Reply("done")

    return complete


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_labelled_regression_row(case):
    result = handle_turn(
        {"messages": []},
        case["input"],
        complete_fn=_complete_for(case),
        crossref=_ShuCrossref(),
        datacite=_DataCite(),
    )
    expected = case.get("expected_labels") or [case["expected_label"]]
    assert labels_in(result["response"]) == expected
    rows = _table_rows(result["response"])
    assert len(rows) == len(expected)
    blob = "\n".join(rows)
    for snippet in case.get("row_contains") or []:
        assert snippet in blob
    for snippet in case.get("each_row_contains") or []:
        assert all(snippet in row for row in rows)
    for snippet in case.get("row_excludes") or []:
        assert snippet not in blob
    if case.get("llm_items") is not None:
        assert any(
            call.get("agent") == "citation-extractor" and "parsed_by" in call["result"]
            for call in result["tool_calls"]
        )
        assert any(
            call["name"] == "record_status" and call["args"].get("parsed_by") == "llm"
            for call in result["tool_calls"]
        )
