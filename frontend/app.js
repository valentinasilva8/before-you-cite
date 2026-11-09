const log = document.querySelector("#log");
const tools = document.querySelector("#tools");
const form = document.querySelector("#composer");
const question = document.querySelector("#question");
const samples = document.querySelector("#samples");
const preview = document.querySelector("#preview");
const previewList = document.querySelector("#preview-list");
const previewTruncated = document.querySelector("#preview-truncated");
const run = document.querySelector("#run");
let sessionId = null;
let previewState = [];
let previewTimer = null;
let previewRequest = 0;
let healthMeta = { short: "", rows: null };

const labels = {
  chatgpt_link: "DOI link",
  chatgpt_citation: "Full citation",
  chatgpt_nature: "Article URL",
  chatgpt_clean: "Reference with DOI",
};

const SEVERITY = {
  "DO NOT CITE": 0,
  "DOESN'T CHECK OUT": 1,
  "CHECK FIRST": 2,
  "UNCONFIRMED": 3,
  "NO ISSUES FOUND": 4,
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

function addResult(checked, node) {
  const card = document.createElement("article");
  card.className = "result-card";
  const header = document.createElement("p");
  header.className = "result-head";
  const time = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const snippet = String(checked || "").replace(/\s+/g, " ").trim().slice(0, 80);
  header.textContent = `${time} · ${snippet}`;
  card.append(header, node);
  log.prepend(card);
  card.scrollIntoView({ block: "nearest" });
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
  const readings = readingsFrom(calls);
  const records = parsed.rows.map((row, index) => ({
    n: row[0],
    citation: cites[index] || "",
    verdict: splitVerdict(row[1]).label,
    reason: splitVerdict(row[1]).reason,
    found: cleanCell(row[2]),
    action: cleanCell(row[3]),
    order: index,
    reading: readings && readings[index] ? readings[index] : null,
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
  const after = notesAfterTable(parsed.after);
  if (after) {
    const rest = document.createElement("div");
    rest.className = "after-table";
    rest.textContent = after;
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

function splitVerdict(cell) {
  const parts = String(cell || "").split("—");
  return { label: parts[0].trim(), reason: parts.slice(1).join("—").trim() };
}

function notesAfterTable(text) {
  const kept = [];
  for (const line of String(text || "").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.includes("```") || trimmed.split("|").length > 2) {
      continue;
    }
    kept.push(trimmed);
  }
  return kept.join("\n").trim();
}

function summaryBanner(records) {
  const counts = {};
  for (const label of Object.keys(SEVERITY)) {
    counts[label] = 0;
  }
  for (const record of records) {
    counts[record.verdict] = (counts[record.verdict] || 0) + 1;
  }
  const parts = Object.keys(SEVERITY)
    .filter((label) => counts[label])
    .map((label) => `${counts[label]} ${label.toLowerCase()}`);
  return `${records.length} checked: ${parts.length ? parts.join(", ") : "none"}.`;
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
    row.appendChild(citationCell(record.citation, record.reading));
    const verdict = document.createElement("td");
    const chip = document.createElement("span");
    chip.className = `chip ${chipClass(record.verdict)}`;
    chip.textContent = record.verdict;
    const tip = legendSentence(record.verdict);
    if (tip) {
      chip.title = tip;
    }
    verdict.appendChild(chip);
    if (record.reason) {
      const reason = document.createElement("div");
      reason.className = "chip-reason";
      reason.textContent = record.reason;
      verdict.appendChild(reason);
    }
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

function citationCell(value, reading) {
  const cell = document.createElement("td");
  cell.className = "citation";
  const title = document.createElement("div");
  title.className = "citation-text";
  const full = value || "";
  title.textContent = full;
  if (full) {
    title.title = full;
  }
  cell.appendChild(title);
  const line = readAsLine(reading);
  if (line) {
    cell.appendChild(line);
  }
  return cell;
}

function readingsFrom(calls) {
  try {
    if (!Array.isArray(calls)) return null;
    const call = calls.find((item) => item && item.name === "parsed_references");
    if (!call || typeof call.result !== "string") return null;
    const data = JSON.parse(call.result);
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.items)) return data.items;
  } catch (error) {
    return null;
  }
  return null;
}

function readAsLine(reading) {
  if (!reading || typeof reading !== "object") return null;
  const line = document.createElement("div");
  line.className = "read-as";
  const label = document.createElement("span");
  label.className = "read-label";
  label.textContent = "Read as";
  line.appendChild(label);
  line.appendChild(readField("Title", reading.title));
  line.appendChild(readField("Authors", reading.authors));
  line.appendChild(readField("Year", reading.year));
  line.appendChild(readField("DOI", reading.doi));
  if (reading.parsed_by) {
    const badge = document.createElement("span");
    badge.className = "read-badge";
    badge.textContent = String(reading.parsed_by);
    line.appendChild(badge);
  }
  if (Array.isArray(reading.notes)) {
    for (const note of reading.notes) {
      if (!note) continue;
      const span = document.createElement("span");
      span.className = "read-note";
      span.textContent = String(note);
      line.appendChild(span);
    }
  }
  return line;
}

function readField(name, value) {
  const field = document.createElement("span");
  field.className = "read-field";
  const key = document.createElement("span");
  key.className = "read-key";
  key.textContent = name + " ";
  const shown = document.createElement("span");
  const text = value == null ? "" : String(value).trim();
  if (text) {
    shown.textContent = text;
  } else {
    shown.className = "read-missing";
    shown.textContent = "not found in your paste";
  }
  field.append(key, shown);
  return field;
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
  if (label === "DOESN'T CHECK OUT" || label === "CHECK FIRST") {
    return "chip-amber";
  }
  if (label === "NO ISSUES FOUND") {
    return "chip-blue";
  }
  return "chip-grey";
}

function legendSentence(label) {
  for (const item of document.querySelectorAll(".legend li")) {
    const chip = item.querySelector(".chip");
    if (chip && chip.textContent.trim() === label) {
      const sentence = item.querySelector("span:last-child");
      return sentence ? sentence.textContent.trim() : "";
    }
  }
  return "";
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
        refreshPreview();
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
    pending.textContent = `Checking, this can take a few minutes (${seconds}s)`;
  };
  log.prepend(pending);
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

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runCheck();
});

question.addEventListener("input", () => {
  syncRun();
  clearTimeout(previewTimer);
  previewTimer = setTimeout(refreshPreview, 600);
});

question.addEventListener("paste", () => {
  clearTimeout(previewTimer);
  setTimeout(refreshPreview, 0);
});

question.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
    runCheck();
  }
});

if (run) {
  run.addEventListener("click", runCheck);
}

document.querySelector("#clear").addEventListener("click", async () => {
  if (sessionId) {
    await fetch(`/clear?session_id=${encodeURIComponent(sessionId)}`, { method: "POST" });
  }
  sessionId = null;
  log.replaceChildren(pending);
  pending.hidden = true;
  pending.textContent = "";
  tools.innerHTML = "";
  clearPreview();
  syncRun();
});

const PREVIEW_FIELDS = [
  ["title", "Title"],
  ["authors", "Authors"],
  ["year", "Year"],
  ["doi", "DOI"],
];

function foldText(value) {
  return String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function fieldAllowed(value, parsedValue, raw) {
  const text = String(value || "").trim();
  if (!text) return true;
  if (foldText(text) === foldText(parsedValue)) return true;
  const folded = foldText(text);
  return Boolean(folded) && foldText(raw).includes(folded);
}

function previewProblems(item, fields) {
  if (!item || item.parsed_by === "unreadable") return [];
  const problems = [];
  for (const [key] of PREVIEW_FIELDS) {
    if (!fieldAllowed(fields[key], item[key], item.raw)) problems.push(key);
  }
  return problems;
}

function rowUnchanged(item, fields) {
  return PREVIEW_FIELDS.every(([key]) => foldText(fields[key]) === foldText(item[key]));
}

function sentence(text) {
  const value = String(text || "").trim();
  if (!value) return "";
  return /[.!?]$/.test(value) ? value : `${value}.`;
}

function lineForRow(item, fields) {
  if (!item || item.parsed_by === "unreadable" || rowUnchanged(item, fields)) {
    return String((item && item.raw) || "");
  }
  const authors = String(fields.authors || "").trim();
  const year = String(fields.year || "").trim();
  const title = String(fields.title || "").trim();
  const doi = String(fields.doi || "").trim();
  const parts = [];
  if (authors && year) parts.push(`${authors} (${year}).`);
  else if (authors) parts.push(sentence(authors));
  else if (year) parts.push(`(${year}).`);
  if (title) {
    const bare = title.replace(/^"|"$/g, "");
    parts.push(year ? sentence(bare) : sentence(`"${bare}"`));
  }
  if (doi) parts.push(doi);
  return parts.join(" ").trim();
}

function messageForPreview(entries) {
  const lines = [];
  for (const entry of entries || []) {
    if (previewProblems(entry.item, entry.fields).length) {
      return { ok: false, message: "" };
    }
    const line = lineForRow(entry.item, entry.fields);
    if (line) lines.push(line);
  }
  return { ok: true, message: lines.join("\n") };
}

function previewEntries() {
  return previewState.map((item, index) => {
    const fields = {};
    const row = previewList.children[index];
    for (const input of row.querySelectorAll("input")) {
      fields[input.dataset.field] = input.value;
    }
    return { item, fields };
  });
}

function showProblems(index, problems) {
  const row = previewList.children[index];
  for (const input of row.querySelectorAll("input")) {
    const problem = input.parentElement.querySelector(".preview-problem");
    const bad = problems.includes(input.dataset.field);
    problem.hidden = !bad;
    problem.textContent = bad ? "Use text from this line, or clear the field." : "";
  }
}

function clearPreview() {
  previewState = [];
  if (previewList) previewList.replaceChildren();
  if (preview) preview.hidden = true;
  if (previewTruncated) previewTruncated.hidden = true;
  syncRun();
}

function renderPreview(items, truncated) {
  previewState = Array.isArray(items) ? items : [];
  previewList.replaceChildren();
  previewState.forEach((item, index) => {
    const row = document.createElement("article");
    row.className = "preview-row";
    const raw = document.createElement("p");
    raw.className = "preview-raw";
    raw.textContent = item.raw || "";
    row.appendChild(raw);
    if (item.parsed_by) {
      const badge = document.createElement("span");
      badge.className = "read-badge";
      badge.textContent = String(item.parsed_by);
      row.appendChild(badge);
    }
    for (const note of item.notes || []) {
      if (!note) continue;
      const span = document.createElement("span");
      span.className = "read-note";
      span.textContent = String(note);
      row.appendChild(span);
    }
    const fields = document.createElement("div");
    fields.className = "preview-fields";
    const locked = item.parsed_by === "unreadable";
    for (const [key, label] of PREVIEW_FIELDS) {
      const labelEl = document.createElement("label");
      labelEl.textContent = `${label} `;
      const input = document.createElement("input");
      input.type = "text";
      input.dataset.field = key;
      input.value = item[key] || "";
      input.disabled = locked;
      const problem = document.createElement("p");
      problem.className = "preview-problem";
      problem.hidden = true;
      input.addEventListener("input", () => {
        const allowed = locked || fieldAllowed(input.value, item[key], item.raw);
        problem.hidden = allowed;
        problem.textContent = allowed ? "" : "Use text from this line, or clear the field.";
      });
      labelEl.append(input, problem);
      fields.appendChild(labelEl);
    }
    row.appendChild(fields);
    previewList.appendChild(row);
  });
  previewTruncated.hidden = !truncated;
  preview.hidden = false;
  syncRun();
}

async function refreshPreview() {
  const message = question.value.trim();
  const token = ++previewRequest;
  syncRun();
  if (!message) {
    clearPreview();
    return;
  }
  try {
    const parsed = await requestParse(message);
    if (token !== previewRequest) return;
    if (!parsed || !parsed.items.length) {
      clearPreview();
      return;
    }
    renderPreview(parsed.items, Boolean(parsed.truncated));
  } catch (error) {
    if (token !== previewRequest) return;
  }
}

function syncRun() {
  if (run) run.disabled = !question.value.trim();
}

function runCheck() {
  const raw = question.value.trim();
  if (!raw) return;
  if (!previewState.length) {
    sendChat(raw);
    return;
  }
  const built = messageForPreview(previewEntries());
  if (!built.ok) {
    previewEntries().forEach((entry, index) => {
      showProblems(index, previewProblems(entry.item, entry.fields));
    });
    return;
  }
  if (!built.message) {
    sendChat(raw);
    return;
  }
  sendChat(built.message);
}

async function requestParse(message) {
  const response = await fetch("/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, fallback: false }),
  });
  if (!response.ok) return null;
  try {
    const body = await response.json();
    if (!body || !Array.isArray(body.items)) return null;
    return body;
  } catch (error) {
    return null;
  }
}

function failureCard(checked, text) {
  const node = document.createElement("div");
  node.className = "bubble assistant";
  node.textContent = text;
  addResult(checked, node);
}

async function sendChat(message) {
  if (run) run.disabled = true;
  startPending();
  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    if (!response.ok) {
      clearPending();
      failureCard(message, `The audit request failed (HTTP ${response.status}). Nothing was checked. Try again.`);
      return;
    }
    let body;
    try {
      body = await response.json();
    } catch (error) {
      clearPending();
      failureCard(message, "The audit request returned a response that was not JSON. Nothing was checked. Try again.");
      return;
    }
    sessionId = body.session_id || sessionId;
    clearPending();
    addResult(message, renderAnswer(body.response || "No response.", body.tool_calls || []));
    showTools(body.tool_calls || []);
  } catch (error) {
    clearPending();
    failureCard(message, "The audit request did not reach the server. Check the connection and try again.");
  } finally {
    syncRun();
  }
}

loadMeta();
