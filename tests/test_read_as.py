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


def test_plain_answer_keeps_line_breaks(tmp_path):
    assert CHROME, "google-chrome is required to render a plain answer"
    (tmp_path / "app.js").write_text((ROOT / "frontend" / "app.js").read_text())
    (tmp_path / "styles.css").write_text((ROOT / "frontend" / "styles.css").read_text())
    page = tmp_path / "plain.html"
    page.write_text(
        """<!DOCTYPE html>
<html lang="en">
<head><link rel="stylesheet" href="styles.css"></head>
<body>
  <span id="rows"></span>
  <div id="samples"></div>
  <p id="pending" hidden></p>
  <form id="composer"><textarea id="question"></textarea><button id="send" type="submit">Ask</button></form>
  <button id="edit" type="button">Edit</button>
  <button id="clear" type="button">Clear</button>
  <div id="preview" hidden><div id="preview-list"></div><p id="preview-truncated" hidden></p><button id="run" type="button"></button></div>
  <div id="log"></div>
  <div id="tools"></div>
  <script src="app.js"></script>
  <script>
    const text = "Top 8 publishers\\n\\nHindawi: 11,524 notice rows\\n  Reason tokens (rows): A (1)\\n  Batch-like dates (rows): 1/24/2024 (2)";
    const node = renderAnswer(text, [], "");
    document.body.appendChild(node);
    const style = getComputedStyle(node);
    const kept = node.textContent === text && !node.querySelector("table");
    document.body.setAttribute("data-space", style.whiteSpace);
    document.body.setAttribute("data-kept", kept ? "yes" : "no");
  </script>
</body>
</html>
"""
    )
    completed = subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-first-run",
            f"--user-data-dir={tmp_path / 'chrome-plain'}",
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
    assert 'data-kept="yes"' in dom
    assert 'data-space="pre-wrap"' in dom or 'data-space="pre-line"' in dom


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


DOI_ONLY_PAGE = """<!DOCTYPE html>
<html lang="en">
<body>
  <span id="commit"><span id="when"></span> <span id="rows"></span></span>
  <div id="samples"></div>
  <p id="pending" hidden></p>
  <form id="composer"><textarea id="question"></textarea></form>
  <button id="run" type="button">Run check</button>
  <button id="clear" type="button">Clear</button>
  <button id="try-doi" type="button">Reference with DOI</button>
  <div id="preview" hidden><div id="preview-list"></div><p id="preview-truncated" hidden></p></div>
  <div id="log"></div>
  <div id="tools"></div>
  <script>
    window.fetch = (url) => {
      const path = String(url);
      if (path.indexOf("/health") !== -1) {
        return Promise.resolve({ ok: true, json: async () => ({ commit_short: "fb5f174f", committed_at: "2026-11-03", rows: 73597 }) });
      }
      if (path.indexOf("/samples") !== -1) {
        return Promise.resolve({ ok: true, json: async () => ({ prompts: { doi_link: "first prompt", reference_with_doi: "the doi prompt" } }) });
      }
      return Promise.resolve({ ok: false, json: async () => ({}) });
    };
  </script>
  <script src="app.js"></script>
  <script>
    const table = [
      "| # | Verdict | What we found | What to do |",
      "| --- | --- | --- | --- |",
      "| 1 | DO NOT CITE | Found it | Leave it out |",
      "| 2 | DO NOT CITE | Found it | Leave it out |"
    ].join("\\n");
    const calls = [{
      agent: "(harness)",
      name: "parsed_references",
      args: {},
      result: JSON.stringify([
        { raw: "https://doi.org/10.3390/nano10122325", title: "", authors: "", year: "", doi: "10.3390/nano10122325", url: "", parsed_by: "rules", notes: [] },
        { raw: "A title only line here", title: "A title only line here", authors: "", year: "", doi: "", url: "", parsed_by: "ai", notes: [] }
      ])
    }];
    const node = renderAnswer(table, calls);
    document.body.appendChild(node);
    const lines = node.querySelectorAll(".read-as");
    const doiLine = lines[0] ? lines[0].textContent : "";
    const titleLine = lines[1] ? lines[1].textContent : "";
    document.body.setAttribute("data-doi-only", (
      doiLine.includes("DOI 10.3390/nano10122325")
      && doiLine.includes("Only a DOI was pasted.")
      && doiLine.includes("rules")
      && !doiLine.includes("not found in your paste")
      && !doiLine.includes("Title")
    ) ? "yes" : "no");
    document.body.setAttribute("data-partial", (
      titleLine.includes("A title only line here")
      && titleLine.includes("not found in your paste")
      && titleLine.includes("ai")
      && !titleLine.includes("Only a DOI was pasted.")
    ) ? "yes" : "no");
    const chip = document.querySelector('#samples button[data-key="reference_with_doi"]');
    document.querySelector("#try-doi").click();
    document.body.setAttribute("data-try", chip && document.querySelector("#question").value === "the doi prompt" ? "yes" : "no");
    const meta = document.querySelector("#commit").title === "Retraction Watch snapshot fb5f174f"
      && document.querySelector("#rows").textContent === "73,597 notices";
    document.body.setAttribute("data-meta", meta ? "yes" : "no");
  </script>
</body>
</html>
"""


def test_doi_only_read_as_and_the_try_link(tmp_path):
    assert CHROME, "google-chrome is required to render the Read as line"
    (tmp_path / "app.js").write_text((ROOT / "frontend" / "app.js").read_text())
    page = tmp_path / "doi-only.html"
    page.write_text(DOI_ONLY_PAGE)
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
    assert 'data-doi-only="yes"' in dom
    assert 'data-partial="yes"' in dom
    assert 'data-try="yes"' in dom
    assert 'data-meta="yes"' in dom


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
    const kept = "Ada (2020). A paper that stays. https://doi.org/10.1000/keep";
    const pasted = [kept, "short title", "other pasted title"].join("\\n");
    document.querySelector("#question").value = pasted;
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
      "DOI: 10.1000/abc",
      "Query: other pasted title",
      "1. A different paper",
      "DOI: 10.2000/xyz"
    ].join("\\n");
    const node = renderAnswer(answer, [], pasted);
    document.body.appendChild(node);
    const note = node.querySelector(".confirm-note");
    const summary = node.querySelector(".summary");
    const choices = node.querySelector(".title-choices");
    const foot = node.querySelector(".snapshot-foot");
    const blocks = node.querySelectorAll(".title-choice-block");
    const first = blocks[0];
    const second = blocks[1];
    const button = first && first.querySelector(".title-choice");
    const noteFirst = Boolean(note && summary && (note.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING));
    const underTable = Boolean(foot && choices && (foot.compareDocumentPosition(choices) & Node.DOCUMENT_POSITION_FOLLOWING));
    const firstLabel = "No paper matched this title: short title. Is this what you meant? Click one below and the check runs again for that paper.";
    const secondLabel = "No paper matched this title: other pasted title. Is this what you meant? Click one below and the check runs again for that paper.";
    document.body.setAttribute("data-note", note && note.textContent.startsWith("Confirm which title you meant") ? "yes" : "no");
    document.body.setAttribute("data-order", noteFirst ? "yes" : "no");
    document.body.setAttribute("data-under", underTable ? "yes" : "no");
    document.body.setAttribute("data-query", node.textContent.includes("short title") ? "yes" : "no");
    document.body.setAttribute("data-writer", node.textContent.includes("A writer note stays on the result.") ? "yes" : "no");
    document.body.setAttribute("data-blocks", String(blocks.length));
    document.body.setAttribute("data-first", first && first.querySelector(".choices-label") && first.querySelector(".choices-label").textContent === firstLabel ? "yes" : "no");
    document.body.setAttribute("data-second", second && second.querySelector(".choices-label") && second.querySelector(".choices-label").textContent === secondLabel ? "yes" : "no");
    const own = Boolean(
      first && second
      && first.textContent.includes("10.1000/abc")
      && !first.textContent.includes("10.2000/xyz")
      && second.textContent.includes("10.2000/xyz")
      && !second.textContent.includes("10.1000/abc")
    );
    document.body.setAttribute("data-own", own ? "yes" : "no");
    const showsPaper = Boolean(
      button
      && button.textContent.includes("Longer title about damages")
      && button.querySelector(".choice-doi")
      && button.querySelector(".choice-doi").textContent === "10.1000/abc"
    );
    document.body.setAttribute("data-button", showsPaper ? "yes" : "no");
    let ran = "no";
    let sentMessage = "";
    window.fetch = (url, options) => {
      if (String(url).indexOf("/chat") !== -1) {
        ran = "yes";
        try {
          sentMessage = JSON.parse(options.body).message;
        } catch (error) {
          sentMessage = "";
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ response: "Checked.", session_id: "s", tool_calls: [] }),
        });
      }
      return Promise.resolve({ ok: false, json: async () => ({}) });
    };
    button.click();
    const chosen = '"Longer title about damages" https://doi.org/10.1000/abc';
    const expected = [kept, chosen, "other pasted title"].join("\\n");
    document.body.setAttribute("data-replaced", document.querySelector("#question").value === expected ? "yes" : "no");
    document.body.setAttribute("data-ran", ran);
    document.body.setAttribute("data-same", sentMessage === expected ? "yes" : "no");
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
    assert 'data-blocks="2"' in dom
    assert 'data-first="yes"' in dom
    assert 'data-second="yes"' in dom
    assert 'data-own="yes"' in dom
    assert 'data-button="yes"' in dom
    assert 'data-replaced="yes"' in dom
    assert 'data-ran="yes"' in dom
    assert 'data-same="yes"' in dom
