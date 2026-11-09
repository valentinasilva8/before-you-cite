"""Labelled rows checked against the frozen extract and the existing fakes."""

import json
from pathlib import Path

import pytest

from retraction_agent.orchestrate import handle_turn
from retraction_agent.verdicts import labels_in
from tests.fakes import scripted_complete
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


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_labelled_regression_row(case):
    result = handle_turn(
        {"messages": []},
        case["input"],
        complete_fn=scripted_complete("Snapshot fb5f174f."),
        crossref=_AgencyCrossref(),
        datacite=_DataCite(),
    )
    assert labels_in(result["response"]) == [case["expected_label"]]
    rows = _table_rows(result["response"])
    assert len(rows) == 1
    row = rows[0]
    for snippet in case.get("row_contains") or []:
        assert snippet in row
    for snippet in case.get("row_excludes") or []:
        assert snippet not in row
