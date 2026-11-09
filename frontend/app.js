const log = document.querySelector("#log");
const tools = document.querySelector("#tools");
const form = document.querySelector("#composer");
const question = document.querySelector("#question");
const send = document.querySelector("#send");
const samples = document.querySelector("#samples");
let sessionId = null;
let healthMeta = { short: "", rows: null };

const labels = {
  sample1_turn1: "Sample 1, turn 1",
  sample1_turn2: "Sample 1, turn 2",
  sample2: "Sample 2",
  sample3: "Sample 3",
  sample4: "Sample 4",
};

const SEVERITY = {
  "DO NOT CITE": 0,
  "WRONG LINK": 1,
  "WRONG KIND OF LINK": 2,
  "NOT FOUND": 3,
};

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function addBubble(role, text, calls) {
  const node = role === "assistant" ? renderAnswer(text, calls) : document.createElement("div");
  if (role !== "assistant") {
    node.className = `bubble ${role}`;
    node.textContent = text;
  }
  log.appendChild(node);
  log.scrollTop = log.scrollHeight;
}

function renderAnswer(text, calls) {
  const node = document.createElement("div");
  node.className = "bubble assistant";
  const parsed = parseVerdictTable(text);
  if (!parsed) {
    node.textContent = text;
    return node;
  }
  const cites = citationsFrom(calls);
  const records = parsed.rows.map((row, index) => ({
    n: row[0],
    citation: cites[index] || "",
    verdict: row[1],
    found: cleanCell(row[2]),
    action: cleanCell(row[3]),
    order: index,
  }));
  const view = { records, original: false };
  const banner = document.createElement("p");
  banner.className = "summary";
  const actions = document.createElement("div");
  actions.className = "table-actions";
  const sortButton = document.createElement("button");
  sortButton.type = "button";
  sortButton.className = "sort-toggle";
  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.textContent = "Copy report";
  const csvButton = document.createElement("button");
  csvButton.type = "button";
  csvButton.textContent = "Download CSV";
  actions.append(sortButton, copyButton, csvButton);
  const tableHost = document.createElement("div");
  tableHost.className = "table-host";
  const snapshot = document.createElement("p");
  snapshot.className = "snapshot-foot";
  snapshot.textContent = snapshotLine();
  node.append(banner, actions, tableHost, snapshot);
  if (parsed.after) {
    const rest = document.createElement("div");
    rest.className = "after-table";
    rest.textContent = parsed.after;
    node.appendChild(rest);
  }

  function paint() {
    const shown = view.original ? records.slice() : sortBySeverity(records);
    banner.textContent = summaryBanner(records);
    sortButton.textContent = view.original ? "Sort by severity" : "Show original order";
    tableHost.replaceChildren(renderRecords(shown));
  }

  sortButton.addEventListener("click", () => {
    view.original = !view.original;
    paint();
  });
  copyButton.addEventListener("click", async () => {
    const markdown = markdownTable(view.original ? records : sortBySeverity(records));
    try {
      await navigator.clipboard.writeText(markdown);
      copyButton.textContent = "Copied";
    } catch (error) {
      copyButton.textContent = "Copy failed";
    }
    window.setTimeout(() => {
      copyButton.textContent = "Copy report";
    }, 1500);
  });
  csvButton.addEventListener("click", () => {
    downloadCsv(view.original ? records : sortBySeverity(records));
  });
  paint();
  return node;
}

function parseVerdictTable(text) {
  const lines = String(text || "").split("\n");
  const start = lines.findIndex((line) => line.trim().startsWith("| # | Verdict |"));
  if (start < 0) {
    return null;
  }
  let end = start;
  while (end < lines.length && lines[end].trim().startsWith("|")) {
    end += 1;
  }
  const rows = [];
  for (const line of lines.slice(start, end)) {
    const cells = line.split("|").slice(1, -1).map((cell) => cell.trim());
    if (cells.length < 4 || cells[1] === "Verdict" || cells.every((cell) => /^:?-+:?$/.test(cell))) {
      continue;
    }
    rows.push(cells);
  }
  return { rows, after: lines.slice(end).join("\n").trim() };
}

function citationsFrom(calls) {
  const cites = [];
  for (const call of calls || []) {
    if (call.name !== "record_status") {
      continue;
    }
    const args = call.args || {};
    cites.push(String(args.title || args.doi || args.raw || "").trim());
  }
  return cites;
}

function cleanCell(value) {
  return String(value || "")
    .replace(/,?\s*snapshot\s+[0-9a-f]{7,40}\.?/gi, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+\./g, ".")
    .trim();
}

function summaryBanner(records) {
  let doNot = 0;
  let wrong = 0;
  let missing = 0;
  let unchecked = 0;
  let other = 0;
  for (const record of records) {
    if (record.verdict === "DO NOT CITE") {
      doNot += 1;
    } else if (record.verdict === "WRONG LINK" || record.verdict === "WRONG KIND OF LINK") {
      wrong += 1;
    } else if (record.verdict === "NOT FOUND") {
      missing += 1;
    } else if (record.verdict === "COULD NOT VERIFY" || record.verdict === "FOUND CAN'T CHECK RETRACTIONS") {
      unchecked += 1;
    } else {
      other += 1;
    }
  }
  return `${records.length} checked: ${doNot} do not cite, ${wrong} wrong link, ${missing} not found, ${unchecked} could not be checked, ${other} other.`;
}

function sortBySeverity(records) {
  return records
    .map((record, index) => ({ record, index }))
    .sort((left, right) => {
      const rank = (SEVERITY[left.record.verdict] ?? 4) - (SEVERITY[right.record.verdict] ?? 4);
      return rank || left.record.order - right.record.order;
    })
    .map((item) => item.record);
}

function renderRecords(records) {
  const table = document.createElement("table");
  table.className = "verdicts";
  const head = document.createElement("tr");
  for (const label of ["#", "Citation", "Verdict", "What we found", "What to do"]) {
    const cell = document.createElement("th");
    cell.textContent = label;
    head.appendChild(cell);
  }
  table.appendChild(head);
  for (const record of records) {
    const row = document.createElement("tr");
    row.appendChild(textCell(record.n));
    row.appendChild(citationCell(record.citation));
    const verdict = document.createElement("td");
    const chip = document.createElement("span");
    chip.className = `chip ${chipClass(record.verdict)}`;
    chip.textContent = record.verdict;
    verdict.appendChild(chip);
    row.appendChild(verdict);
    row.appendChild(textCell(record.found));
    row.appendChild(textCell(record.action));
    table.appendChild(row);
  }
  return table;
}

function textCell(value) {
  const cell = document.createElement("td");
  cell.textContent = value;
  return cell;
}

function citationCell(value) {
  const cell = document.createElement("td");
  cell.className = "citation";
  const full = value || "";
  cell.textContent = full;
  if (full) {
    cell.title = full;
  }
  return cell;
}

function markdownTable(records) {
  const lines = [
    "| # | Citation | Verdict | What we found | What to do |",
    "| --- | --- | --- | --- | --- |",
  ];
  for (const record of records) {
    lines.push(
      `| ${md(record.n)} | ${md(record.citation)} | ${md(record.verdict)} | ${md(record.found)} | ${md(record.action)} |`
    );
  }
  const foot = snapshotLine();
  if (foot) {
    lines.push("", foot);
  }
  return lines.join("\n");
}

function md(value) {
  return String(value || "").replace(/\|/g, "/").replace(/\s+/g, " ").trim();
}

function csvField(value) {
  const text = String(value || "");
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function downloadCsv(records) {
  const lines = [["#", "Citation", "Verdict", "What we found", "What to do"].map(csvField).join(",")];
  for (const record of records) {
    lines.push([record.n, record.citation, record.verdict, record.found, record.action].map(csvField).join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "before-you-cite.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

function snapshotLine() {
  if (!healthMeta.short || healthMeta.rows == null) {
    return "";
  }
  return `Retraction Watch snapshot ${healthMeta.short}, ${healthMeta.rows} rows`;
}

function chipClass(label) {
  if (label === "DO NOT CITE") {
    return "chip-red";
  }
  if (
    label === "CHECK FIRST" ||
    label === "WRONG LINK" ||
    label === "WRONG KIND OF LINK" ||
    label === "NOT FOUND" ||
    label === "COULD NOT VERIFY"
  ) {
    return "chip-amber";
  }
  if (label === "NO NOTICE FOUND") {
    return "chip-blue";
  }
  return "chip-grey";
}

function showTools(calls) {
  tools.innerHTML = "";
  if (!calls || !calls.length) {
    tools.innerHTML = "<p class='aside-note'>No tools on this turn.</p>";
    return;
  }
  for (const call of calls) {
    const block = document.createElement("article");
    block.className = "call";
    const args = escapeHtml(JSON.stringify(call.args, null, 2));
    const result = escapeHtml(call.result);
    block.innerHTML = `
      <div class="who">${escapeHtml(call.agent || "")}</div>
      <div class="name">${escapeHtml(call.name || "")}</div>
      <pre>${args}</pre>
      <pre>${result}</pre>
    `;
    tools.appendChild(block);
  }
}

async function loadMeta() {
  try {
    const health = await fetch("/health");
    const body = await health.json();
    healthMeta = { short: body.commit_short || body.commit || "", rows: body.rows };
    document.querySelector("#commit").textContent = healthMeta.short;
    document.querySelector("#when").textContent = (body.committed_at || "").slice(0, 10);
    document.querySelector("#rows").textContent = `${Number(body.rows).toLocaleString("en-US")} notice rows`;
  } catch (error) {
    document.querySelector("#rows").textContent = "Extract did not load";
  }
  try {
    const response = await fetch("/samples");
    const body = await response.json();
    samples.innerHTML = "";
    for (const [key, prompt] of Object.entries(body.prompts || {})) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = labels[key] || key;
      button.addEventListener("click", () => {
        question.value = prompt;
        question.focus();
      });
      samples.appendChild(button);
    }
  } catch (error) {
    samples.textContent = "Sample prompts did not load.";
  }
}

const pending = document.querySelector("#pending");
let pendingTimer = null;

function startPending() {
  const started = Date.now();
  const tick = () => {
    const seconds = Math.floor((Date.now() - started) / 1000);
    pending.hidden = false;
    pending.textContent = `Audits can take a few minutes (${seconds}s)`;
  };
  tick();
  pendingTimer = setInterval(tick, 1000);
}

function clearPending() {
  if (pendingTimer) {
    clearInterval(pendingTimer);
    pendingTimer = null;
  }
  pending.hidden = true;
  pending.textContent = "";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = question.value.trim();
  if (!message) return;
  addBubble("user", message);
  send.disabled = true;
  startPending();
  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    if (!response.ok) {
      addBubble("assistant", `The audit request failed (HTTP ${response.status}). Nothing was checked. Try again.`);
      return;
    }
    let body;
    try {
      body = await response.json();
    } catch (error) {
      addBubble("assistant", "The audit request returned a response that was not JSON. Nothing was checked. Try again.");
      return;
    }
    sessionId = body.session_id || sessionId;
    addBubble("assistant", body.response || "No response.", body.tool_calls || []);
    showTools(body.tool_calls || []);
  } catch (error) {
    addBubble("assistant", "The audit request did not reach the server. Check the connection and try again.");
  } finally {
    clearPending();
    send.disabled = false;
  }
});

document.querySelector("#edit").addEventListener("click", () => {
  question.focus();
  question.scrollIntoView({ block: "center" });
});

document.querySelector("#clear").addEventListener("click", async () => {
  if (sessionId) {
    await fetch(`/clear?session_id=${encodeURIComponent(sessionId)}`, { method: "POST" });
  }
  sessionId = null;
  log.innerHTML = "";
  tools.innerHTML = "";
});

loadMeta();
