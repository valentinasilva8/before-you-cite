import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHROME = "/usr/bin/google-chrome-stable" if Path("/usr/bin/google-chrome-stable").exists() else shutil.which("google-chrome")

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
  <div id="preview" hidden><div id="preview-list"></div><p id="preview-truncated" hidden></p><button id="run" type="button"></button></div>
  <div id="log"></div>
  <div id="tools"></div>
  <script src="app.js"></script>
  <script>
    const hostile = "<" + "script>alert(1)</" + "script>";
    const note = "<" + "img src=x onerror=alert(1)>";
    const table = [
      "| # | Verdict | What we found | What to do |",
      "| --- | --- | --- | --- |",
      "| 1 | DO NOT CITE | Found it | Leave it out |"
    ].join("\\n");
    const calls = [{
      agent: "(harness)",
      name: "parsed_references",
      args: {},
      result: JSON.stringify([{
        raw: hostile,
        title: hostile,
        authors: "",
        year: "",
        doi: "",
        url: "",
        parsed_by: "rules",
        notes: [note]
      }])
    }];
    const node = renderAnswer(table, calls);
    document.body.appendChild(node);
    const read = node.querySelector(".read-as");
    const text = read ? read.textContent : "";
    const escaped = Boolean(
      read
      && text.includes("Read as")
      && text.includes(hostile)
      && text.includes(note)
      && text.includes("not found in your paste")
      && text.includes("rules")
      && !read.querySelector("script")
      && !read.querySelector("img")
    );
    document.body.setAttribute("data-ok", escaped ? "yes" : "no");
    const quiet = renderAnswer(table, []);
    document.body.setAttribute("data-quiet", quiet.querySelector(".read-as") ? "no" : "yes");
    const broken = renderAnswer(table, [{name: "parsed_references", result: "{"}]);
    document.body.setAttribute("data-broken", broken.querySelector(".read-as") ? "no" : "yes");
  </script>
</body>
</html>
"""


def test_read_as_line_renders_and_escapes_html(tmp_path):
    assert CHROME, "google-chrome is required to render the Read as line"
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
    assert 'data-ok="yes"' in dom
    assert 'data-quiet="yes"' in dom
    assert 'data-broken="yes"' in dom
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in dom
    assert "<script>alert(1)</script>" not in dom
    assert "<img src=x onerror=alert(1)>" not in dom


CHOICE_PAGE = """<!DOCTYPE html>
<html lang="en">
<body>
  <span id="rows"></span>
  <div id="samples"></div>
  <p id="pending" hidden></p>
  <form id="composer">
    <textarea id="question"></textarea>
    <button id="run" type="button" disabled>Run check</button>
  </form>
  <div id="preview" hidden><div id="preview-list"></div><p id="preview-truncated" hidden></p></div>
  <div id="log"></div>
  <div id="tools"></div>
  <button id="clear" type="button">Clear</button>
  <script src="app.js"></script>
  <script>
    const answer = [
      "Confirm which title you meant. The choices are listed under the table.",
      "",
      "| # | Verdict | What we found | What to do |",
      "| --- | --- | --- | --- |",
      "| 1 | UNCONFIRMED — No matching record found | This title did not match one paper. | Confirm which title you meant. The choices are listed under the table. |",
      "",
      "A writer note stays on the result.",
      "Query: short title",
      "1. Longer title about damages",
      "DOI: 10.1000/abc"
    ].join("\\n");
    const node = renderAnswer(answer, []);
    document.body.appendChild(node);
    const note = node.querySelector(".confirm-note");
    const summary = node.querySelector(".summary");
    const choices = node.querySelector(".title-choices");
    const foot = node.querySelector(".snapshot-foot");
    const button = node.querySelector(".title-choice");
    const noteFirst = Boolean(note && summary && (note.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING));
    const underTable = Boolean(foot && choices && (foot.compareDocumentPosition(choices) & Node.DOCUMENT_POSITION_FOLLOWING));
    document.body.setAttribute("data-note", note && note.textContent.startsWith("Confirm which title you meant") ? "yes" : "no");
    document.body.setAttribute("data-order", noteFirst ? "yes" : "no");
    document.body.setAttribute("data-under", underTable ? "yes" : "no");
    document.body.setAttribute("data-query", node.textContent.includes("short title") ? "yes" : "no");
    document.body.setAttribute("data-writer", node.textContent.includes("A writer note stays on the result.") ? "yes" : "no");
    button.click();
    const filled = document.querySelector("#question").value === '"Longer title about damages" https://doi.org/10.1000/abc';
    document.body.setAttribute("data-filled", filled ? "yes" : "no");
    document.body.setAttribute("data-run", document.querySelector("#run").disabled ? "no" : "yes");
  </script>
</body>
</html>
"""


def test_clicking_a_title_fills_the_box(tmp_path):
    assert CHROME, "google-chrome is required to click a title choice"
    (tmp_path / "app.js").write_text((ROOT / "frontend" / "app.js").read_text())
    page = tmp_path / "page.html"
    page.write_text(CHOICE_PAGE)
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
    assert 'data-note="yes"' in dom
    assert 'data-order="yes"' in dom
    assert 'data-under="yes"' in dom
    assert 'data-query="yes"' in dom
    assert 'data-writer="yes"' in dom
    assert 'data-filled="yes"' in dom
    assert 'data-run="yes"' in dom
