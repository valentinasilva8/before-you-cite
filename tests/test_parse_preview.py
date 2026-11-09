import json
import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from retraction_agent.planning import parse_references
from retraction_agent.reading import parse_message
from tests.fakes import Reply, ToolCall, scripted_complete

ROOT = Path(__file__).resolve().parents[1]
CHROME = "/usr/bin/google-chrome-stable" if Path("/usr/bin/google-chrome-stable").exists() else shutil.which("google-chrome")
PASTED = "Coastal erosion and sediment transport in deltas is the pasted title here."


def _item(index, **fields):
    base = {
        "raw_line_index": index,
        "title": "",
        "authors": "",
        "year": "",
        "venue": "",
        "doi": "",
        "url": "",
    }
    base.update(fields)
    return base


def _complete(items):
    def complete(messages, tools):
        if any(item.get("role") == "tool" for item in messages):
            return Reply("done")
        return Reply("", [ToolCall("submit_extractions", {"items": items})])

    return complete


def test_parse_orders_a_doi_and_an_unreadable_line():
    message = "https://doi.org/10.3390/nano10122325\n1. Smith (2012)."
    result = parse_message(message, complete_fn=scripted_complete())
    assert set(result) == {"items", "truncated"}
    assert result["truncated"] is False
    assert [item["doi"] for item in result["items"]] == ["10.3390/nano10122325", ""]
    assert result["items"][0]["parsed_by"] == "rules"
    assert result["items"][1]["parsed_by"] == "unreadable"
    assert result["items"][1]["raw"].endswith("Smith (2012).")
    dumped = json.dumps(result).casefold()
    assert "crossref" not in dumped
    assert "rw_" not in dumped


def test_parse_keeps_a_verbatim_ai_title_and_rejects_an_invented_one():
    accepted = parse_message(PASTED, complete_fn=_complete([_item(0, title=PASTED.rstrip("."))]))
    assert accepted["items"][0]["parsed_by"] == "ai"
    assert accepted["items"][0]["title"] == PASTED.rstrip(".")
    assert accepted["items"][0]["notes"] == []

    rejected = parse_message(
        PASTED,
        complete_fn=_complete([_item(0, title="Coastal erosion in river deltas is a different title.")]),
    )
    assert rejected["items"][0]["parsed_by"] == "unreadable"
    assert rejected["items"][0]["doi"] == ""
    assert "river" not in rejected["items"][0]["title"]


def test_parse_route_returns_the_same_item_shape():
    client = TestClient(app)
    body = client.post("/parse", json={"message": "https://doi.org/10.3390/nano10122325"}).json()
    assert set(body) == {"items", "truncated"}
    assert body["truncated"] is False
    item = body["items"][0]
    assert set(item) == {"raw", "title", "authors", "year", "doi", "url", "parsed_by", "notes"}
    assert item["doi"] == "10.3390/nano10122325"
    assert item["parsed_by"] == "rules"


def test_parse_reports_the_existing_cap():
    lines = [f"https://doi.org/10.1000/example-{number}" for number in range(1, 27)]
    result = parse_message("\n".join(lines))
    assert result["truncated"] is True
    assert len(result["items"]) == 25
    assert result["items"][0]["doi"] == "10.1000/example-1"
    assert result["items"][-1]["doi"] == "10.1000/example-25"


def test_a_question_has_no_preview_items():
    result = parse_message("Has CRISPR been retracted?", complete_fn=scripted_complete())
    assert result == {"items": [], "truncated": False}


def test_a_confirmed_line_with_a_year_parses_back():
    line = "Shu, L. (2012). Coastal sediment. 10.1000/example"
    assert parse_references(line) == [
        {
            "doi": "10.1000/example",
            "title": "Coastal sediment",
            "author": "Shu, L.",
            "year": "2012",
        }
    ]


PAGE = """<!DOCTYPE html>
<html lang="en">
<body>
  <span id="rows"></span>
  <div id="samples"></div>
  <p id="pending" hidden></p>
  <form id="composer">
    <textarea id="question"></textarea>
    <button id="send" type="submit">Ask</button>
  </form>
  <button id="edit" type="button">Edit</button>
  <button id="clear" type="button">Clear</button>
  <div id="preview" hidden>
    <div id="preview-list"></div>
    <p id="preview-truncated" hidden></p>
    <button id="run" type="button">Run check</button>
  </div>
  <div id="log"></div>
  <div id="tools"></div>
  <script src="app.js"></script>
  <script>
    const hostile = "<" + "script>alert(1)</" + "script>";
    const raw = "Coastal erosion and sediment transport in deltas is the pasted title here.";
    const item = {
      raw: raw,
      title: raw.replace(/\\.$/, ""),
      authors: "",
      year: "",
      doi: "",
      url: "",
      parsed_by: "rules",
      notes: []
    };
    const copied = messageForPreview([{
      item: item,
      fields: { title: "sediment transport in deltas", authors: "", year: "", doi: "" }
    }]);
    document.body.setAttribute(
      "data-copied",
      copied.ok && copied.message.includes("sediment transport in deltas") ? "yes" : "no"
    );
    const invented = messageForPreview([{
      item: item,
      fields: { title: item.title, authors: "", year: "", doi: "10.9999/not-in-the-paste" }
    }]);
    document.body.setAttribute("data-invented", invented.ok ? "accepted" : "rejected");
    const unread = messageForPreview([{
      item: {
        raw: "1. Smith (2012).",
        title: "",
        authors: "",
        year: "",
        doi: "",
        parsed_by: "unreadable",
        notes: []
      },
      fields: { title: "Invented", authors: "No", year: "1999", doi: "10.1/x" }
    }]);
    document.body.setAttribute(
      "data-unread",
      unread.ok && unread.message === "1. Smith (2012)." ? "yes" : "no"
    );
    renderPreview([{
      raw: hostile,
      title: hostile,
      authors: "",
      year: "",
      doi: "",
      url: "",
      parsed_by: "rules",
      notes: ["<" + "img src=x onerror=alert(1)>"]
    }], false);
    const row = document.querySelector(".preview-row");
    const text = row ? row.textContent : "";
    const escaped = Boolean(row && text.includes(hostile) && !row.querySelector("script") && !row.querySelector("img"));
    document.body.setAttribute("data-escaped", escaped ? "yes" : "no");
    const input = row.querySelector("input");
    input.value = "10.9999/typed-not-pasted";
    input.dispatchEvent(new Event("input"));
    const problem = row.querySelector(".preview-problem");
    document.body.setAttribute("data-problem", problem && !problem.hidden && problem.textContent ? "yes" : "no");
  </script>
</body>
</html>
"""


def test_preview_escapes_html_and_refuses_an_invented_field(tmp_path):
    assert CHROME, "google-chrome is required to render the preview"
    (tmp_path / "app.js").write_text((ROOT / "frontend" / "app.js").read_text())
    page = tmp_path / "page.html"
    page.write_text(PAGE)
    completed = subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-first-run",
            f"--user-data-dir={tmp_path / 'chrome-profile'}",
            "--dump-dom",
            page.as_uri(),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    dom = completed.stdout
    assert 'data-copied="yes"' in dom
    assert 'data-invented="rejected"' in dom
    assert 'data-unread="yes"' in dom
    assert 'data-escaped="yes"' in dom
    assert 'data-problem="yes"' in dom
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in dom
    assert "<script>alert(1)</script>" not in dom
    assert "<img src=x onerror=alert(1)>" not in dom
