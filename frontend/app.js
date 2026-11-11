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
let activeSampleKey = null;
let samplePrompts = {};
let previewText = "";

const labels = {
  doi_link: "DOI link",
  reference_with_doi: "Reference with DOI",
  reading_list: "Reading list (8)",
  publisher_question: "Publisher question",
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
  return card;
}

function renderAnswer(text, calls, source) {
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
  const noteLine = confirmNote(parsed.before);
  if (noteLine) {
    const note = document.createElement("p");
    note.className = "confirm-note";
    note.textContent = noteLine;
    node.appendChild(note);
  }
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
  const after = splitAfter(parsed.after);
  if (after.choices.length) {
    node.appendChild(renderChoices(after.choices, source));
  }
  if (after.notes) {
    const rest = document.createElement("div");
    rest.className = "after-table";
    rest.textContent = after.notes;
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
  return {
    rows,
    before: lines.slice(0, start).join("\n").trim(),
    after: lines.slice(end).join("\n").trim(),
  };
}

function confirmNote(before) {
  return String(before || "")
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.startsWith("Confirm which title you meant.")) || "";
}

function splitAfter(text) {
  const lines = String(text || "").split("\n");
  const start = lines.findIndex((line) => line.trim().startsWith("Query:"));
  if (start < 0) {
    return { notes: notesAfterTable(text), choices: [] };
  }
  const choices = [];
  let current = null;
  for (const line of lines.slice(start)) {
    const trimmed = line.trim();
    if (trimmed.startsWith("Query:")) {
      current = { query: trimmed.slice("Query:".length).trim(), options: [] };
      choices.push(current);
      continue;
    }
    const numbered = trimmed.match(/^(\d+)\.\s+(.+)$/);
    if (numbered && current) {
      current.options.push({ title: numbered[2].trim(), doi: "" });
      continue;
    }
    const doi = trimmed.match(/^DOI:\s*(.+)$/i);
    if (doi && current && current.options.length) {
      current.options[current.options.length - 1].doi = doi[1].trim();
    }
  }
  return { notes: notesAfterTable(lines.slice(0, start).join("\n")), choices };
}

function closeTitlePrompt(title) {
  const pasted = String(title || "").trim();
  return `No paper matched this title: ${pasted}. Is this what you meant? Click one below and the check runs again for that paper.`;
}

function renderChoices(groups, source) {
  const wrap = document.createElement("div");
  wrap.className = "title-choices";
  for (const group of groups) {
    if (!group.options.length) continue;
    const block = document.createElement("section");
    block.className = "title-choice-block";
    const heading = document.createElement("p");
    heading.className = "choices-label";
    heading.textContent = closeTitlePrompt(group.query);
    block.appendChild(heading);
    for (const option of group.options) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "title-choice";
      const name = document.createElement("span");
      name.className = "choice-title";
      name.textContent = option.title;
      button.appendChild(name);
      if (option.doi) {
        const id = document.createElement("span");
        id.className = "choice-doi";
        id.textContent = option.doi;
        button.appendChild(id);
      }
      button.addEventListener("click", () => useChoice(group.query, option, source));
      block.appendChild(button);
    }
    wrap.appendChild(block);
  }
  return wrap;
}

function choiceCitation(option) {
  const title = String(option.title || "").trim();
  const doi = String(option.doi || "").replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "").trim();
  const quoted = title ? `"${title}"` : "";
  const link = doi ? `https://doi.org/${doi}` : "";
  return [quoted, link].filter(Boolean).join(" ");
}

function lineToReplace(lines, needle) {
  let best = -1;
  let bestLen = Infinity;
  for (let i = 0; i < lines.length; i++) {
    const folded = foldText(lines[i]);
    if (!folded || !folded.includes(needle)) continue;
    if (folded === needle) return i;
    if (folded.length < bestLen) {
      best = i;
      bestLen = folded.length;
    }
  }
  return best;
}

function replaceCitation(source, pastedTitle, replacement) {
  const text = String(source || "");
  const needle = foldText(pastedTitle);
  if (!text.trim() || !needle) return replacement;
  const lines = text.split("\n");
  const index = lineToReplace(lines, needle);
  if (index < 0) return replacement;
  const next = lines.slice();
  next[index] = replacement;
  return next.join("\n");
}

function useChoice(pastedTitle, option, source) {
  const replacement = choiceCitation(option);
  const stored = source == null ? "" : String(source);
  question.value = replaceCitation(stored, pastedTitle, replacement);
  activeSampleKey = null;
  clearTimeout(previewTimer);
  previewRequest += 1;
  clearPreview();
  runCheck();
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
  if (doiOnly(reading)) {
    line.appendChild(readField("DOI", reading.doi));
    const only = document.createElement("span");
    only.className = "read-only-doi";
    only.textContent = "Only a DOI was pasted.";
    line.appendChild(only);
  } else {
    line.appendChild(readField("Title", reading.title));
    line.appendChild(readField("Authors", reading.authors));
    line.appendChild(readField("Year", reading.year));
    line.appendChild(readField("DOI", reading.doi));
  }
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

function filled(value) {
  return value != null && String(value).trim() !== "";
}

function doiOnly(reading) {
  return !filled(reading.title) && !filled(reading.authors) && !filled(reading.year) && filled(reading.doi);
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
  if (label === "DOESN'T CHECK OUT") {
    return "chip-orange";
  }
  if (label === "CHECK FIRST") {
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

function showToolsPlain(calls) {
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

function showTools(calls) {
  try {
    buildTimeline(calls);
  } catch (error) {
    try {
      tools.replaceChildren();
      showToolsPlain(calls);
    } catch (fallbackError) {
      try {
        tools.replaceChildren();
      } catch (ignored) {
        // Nothing left to clean up.
      }
    }
  }
}

function plural(count, one, many) {
  return `${count} ${count === 1 ? one : many}`;
}

function shortText(value, max = 90) {
  const text = String(value == null ? "" : value).replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max - 3).trim()}...` : text;
}

function endSentence(text) {
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

const TOOL_SUMMARIES = {
  submit_plan(args) {
    if (args.top_publishers) return "Planned a ranking of publishers by notice rows.";
    const refs = Array.isArray(args.references) ? args.references.length : 0;
    const names = [].concat(args.journals || [], args.publishers || []).length;
    if (refs) return `Planned ${plural(refs, "reference", "references")} to check.`;
    if (names) return `Planned a pattern lookup for ${plural(names, "name", "names")}.`;
    return args.action ? `Plan action: ${shortText(args.action, 40)}.` : "";
  },
  submit_gap_plan(args, result) {
    if (result.action === "done") return "Lead decided no more research was needed.";
    const sent = Array.isArray(result.accepted) ? result.accepted.length : 0;
    if (!sent) return "";
    return `Lead found a gap and sent ${plural(sent, "more researcher", "more researchers")}.`;
  },
  submit_extractions(args, result) {
    const items = Array.isArray(result.items) ? result.items : [];
    if (!items.length) return "";
    const passed = items.filter((item) => item && item.passed_copy_check).length;
    return `AI reader read ${plural(items.length, "line", "lines")}, ${passed} passed the copy check.`;
  },
  rw_lookup_doi(args, result) {
    const total = Number(result.total) || 0;
    return total
      ? `Retraction Watch has ${plural(total, "notice row", "notice rows")} for this DOI.`
      : "No Retraction Watch notice for this DOI.";
  },
  rw_lookup_title(args, result) {
    const total = Number(result.total) || 0;
    return total
      ? `Retraction Watch has ${plural(total, "notice row", "notice rows")} for this title.`
      : "No Retraction Watch notice for this title.";
  },
  rw_pattern(args, result) {
    if (result.ok === false) return "Pattern lookup did not run.";
    const rows = Number(result.rows) || 0;
    return endSentence(`${plural(rows, "notice row", "notice rows")} for ${result.field || "name"} ${shortText(result.matched, 60)}`);
  },
  rw_top_publishers(args, result) {
    const list = Array.isArray(result.publishers) ? result.publishers : [];
    if (!list.length) return "";
    const top = list[0] || {};
    const rows = Number(top.notice_rows);
    const lead = top.publisher && Number.isFinite(rows) ? ` Top: ${shortText(top.publisher, 40)} (${rows.toLocaleString("en-US")}).` : "";
    return `Ranked ${plural(list.length, "publisher", "publishers")} by notice rows.${lead}`;
  },
  doi_agency(args, result) {
    if (result.registration === "not_registered") return "No registration agency has this DOI.";
    return result.agency_label ? `Registered with ${shortText(result.agency_label, 40)}.` : "";
  },
  crossref_doi(args, result) {
    if (result.ok === false) return "Crossref lookup did not return a record.";
    const notices = Array.isArray(result.updated_by) ? result.updated_by.length : 0;
    const title = result.title ? endSentence(`Crossref record: ${shortText(result.title, 70)}`) : "Crossref returned a record.";
    return notices ? `${title} ${plural(notices, "linked notice", "linked notices")}.` : title;
  },
  datacite_work(args, result) {
    if (result.ok === false) return "DataCite did not return a record.";
    return result.title ? endSentence(`DataCite record: ${shortText(result.title, 70)}`) : "DataCite returned a record.";
  },
  crossref_title(args, result) {
    if (result.ok === false) return "Crossref title search did not return.";
    const count = Array.isArray(result.candidates) ? result.candidates.length : 0;
    return `${plural(count, "Crossref candidate", "Crossref candidates")}, ${result.clear_match ? "one clear match" : "no clear match"}.`;
  },
};

function summarize(call) {
  try {
    const summary = TOOL_SUMMARIES[call.name];
    if (typeof summary !== "function") return "";
    let result = {};
    try {
      const parsed = JSON.parse(call.result);
      if (parsed && typeof parsed === "object") result = parsed;
    } catch (error) {
      result = {};
    }
    const args = call.args && typeof call.args === "object" ? call.args : {};
    return String(summary(args, result) || "");
  } catch (error) {
    return "";
  }
}

function agentTone(agent) {
  const name = String(agent || "").toLowerCase();
  for (const tone of ["lead", "extractor", "audit", "pattern", "crossref", "writer"]) {
    if (name.includes(tone)) return `tone-${tone}`;
  }
  return "tone-harness";
}

function verdictCounts() {
  const card = log.querySelector(".result-card");
  if (!card) return "";
  const chips = card.querySelectorAll("table.verdicts .chip");
  if (!chips.length) return "";
  const counts = {};
  for (const chip of chips) {
    const label = chip.textContent.trim();
    counts[label] = (counts[label] || 0) + 1;
  }
  const order = Object.keys(SEVERITY).concat(Object.keys(counts).filter((label) => !(label in SEVERITY)));
  const parts = order.filter((label) => counts[label]).map((label) => `${counts[label]} ${label.toLowerCase()}`);
  return `Verdicts: ${parts.join(", ")}.`;
}

let timelineId = 0;

function buildTimeline(calls) {
  if (!Array.isArray(calls) || !calls.length) {
    showToolsPlain(calls);
    return;
  }
  const toggles = [];
  const expand = document.createElement("button");
  expand.type = "button";
  expand.className = "timeline-expand";

  function syncExpand() {
    const open = toggles.length > 0 && toggles.every((item) => item.getAttribute("aria-expanded") === "true");
    expand.setAttribute("aria-expanded", open ? "true" : "false");
    expand.textContent = open ? "Collapse all raw calls" : "Expand all raw calls";
  }

  function setRaw(toggle, raw, open) {
    raw.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.textContent = open ? "Hide raw" : "Show raw";
  }

  const list = document.createElement("ol");
  list.className = "timeline";
  const pairs = [];
  for (const call of calls) {
    const item = call && typeof call === "object" ? call : {};
    const step = document.createElement("li");
    step.className = "timeline-step";
    const head = document.createElement("div");
    head.className = "timeline-head";
    const pill = document.createElement("span");
    pill.className = `timeline-pill ${agentTone(item.agent)}`;
    pill.textContent = String(item.agent || "agent");
    const name = document.createElement("span");
    name.className = "timeline-name";
    name.textContent = String(item.name || "");
    head.append(pill, name);
    step.appendChild(head);
    const summary = summarize(item);
    if (summary) {
      const line = document.createElement("p");
      line.className = "timeline-summary";
      line.textContent = summary;
      step.appendChild(line);
    }
    timelineId += 1;
    const raw = document.createElement("div");
    raw.className = "timeline-raw";
    raw.id = `timeline-raw-${timelineId}`;
    const args = document.createElement("pre");
    args.textContent = JSON.stringify(item.args, null, 2);
    const result = document.createElement("pre");
    result.textContent = String(item.result);
    raw.append(args, result);
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "timeline-raw-toggle";
    toggle.setAttribute("aria-controls", raw.id);
    setRaw(toggle, raw, false);
    toggle.addEventListener("click", () => {
      setRaw(toggle, raw, raw.hidden);
      syncExpand();
    });
    toggles.push(toggle);
    pairs.push([toggle, raw]);
    step.append(toggle, raw);
    list.appendChild(step);
  }
  expand.addEventListener("click", () => {
    const open = expand.getAttribute("aria-expanded") !== "true";
    for (const [toggle, raw] of pairs) setRaw(toggle, raw, open);
    syncExpand();
  });
  syncExpand();
  const nodes = [expand, list];
  const counted = verdictCounts();
  if (counted) {
    const row = document.createElement("p");
    row.className = "timeline-counts";
    row.textContent = counted;
    nodes.push(row);
  }
  tools.replaceChildren(...nodes);
}

async function loadMeta() {
  try {
    const health = await fetch("/health");
    const body = await health.json();
    healthMeta = { short: body.commit_short || body.commit || "", rows: body.rows };
    document.querySelector("#commit").title = `Retraction Watch snapshot ${healthMeta.short}`;
    document.querySelector("#when").textContent = (body.committed_at || "").slice(0, 10);
    document.querySelector("#rows").textContent = `${Number(body.rows).toLocaleString("en-US")} notices`;
  } catch (error) {
    document.querySelector("#rows").textContent = "Data did not load";
  }
  try {
    const response = await fetch("/samples");
    const body = await response.json();
    samples.innerHTML = "";
    for (const [key, prompt] of Object.entries(body.prompts || {})) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.key = key;
      button.textContent = labels[key] || key;
      samplePrompts[key] = prompt;
      button.addEventListener("click", () => {
        question.value = prompt;
        activeSampleKey = key;
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
  activeSampleKey = null;
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

const tryDoi = document.querySelector("#try-doi");
if (tryDoi) {
  tryDoi.addEventListener("click", () => {
    const chip = samples.querySelector('button[data-key="reference_with_doi"]');
    if (chip) chip.click();
  });
}

document.querySelector("#clear").addEventListener("click", async () => {
  activeSampleKey = null;
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
  previewText = "";
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
    previewText = message;
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
  const sampleKey = sampleKeyFor(raw);
  if (!previewState.length) {
    sendChat(raw, sampleKey);
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
    sendChat(raw, sampleKey);
    return;
  }
  sendChat(built.message, sampleKey);
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

function clearInput() {
  question.value = "";
  activeSampleKey = null;
  clearTimeout(previewTimer);
  previewRequest += 1;
  clearPreview();
}

async function sendChat(message, sampleKey = null) {
  const typed = question.value;
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
    const text = body.response || "No response.";
    const card = addResult(message, renderAnswer(text, body.tool_calls || [], message));
    if (sampleKey && !text.startsWith("Model call failed")) {
      try {
        attachCompare(card, sampleKey);
      } catch (error) {
        // The card stays as it is.
      }
    }
    showTools(body.tool_calls || []);
    if (!text.startsWith("Model call failed") && question.value === typed) {
      clearInput();
    }
  } catch (error) {
    clearPending();
    failureCard(message, "The audit request did not reach the server. Check the connection and try again.");
  } finally {
    syncRun();
  }
}

const COMPARE_PREVIEW_CHARS = { reading_list: 600 };
let baselinesPromise = null;
let compareId = 0;

function sampleKeyFor(raw) {
  try {
    if (!activeSampleKey) return null;
    const prompt = samplePrompts[activeSampleKey];
    if (typeof prompt !== "string" || raw !== prompt.trim()) return null;
    if (previewState.length) {
      if (previewText !== raw) return null;
      if (!previewEntries().every((entry) => rowUnchanged(entry.item, entry.fields))) return null;
    }
    return activeSampleKey;
  } catch (error) {
    return null;
  }
}

function loadBaselines() {
  if (!baselinesPromise) {
    try {
      baselinesPromise = fetch("/static/baselines.json")
        .then((response) => (response && response.ok ? response.json() : null))
        .then((data) => (data && typeof data === "object" ? data : null))
        .catch(() => null)
        .then((data) => {
          if (!data) baselinesPromise = null;
          return data;
        });
    } catch (error) {
      baselinesPromise = null;
      return Promise.resolve(null);
    }
  }
  return baselinesPromise;
}

async function attachCompare(card, key) {
  try {
    if (!card || !key) return;
    const data = await loadBaselines();
    const base = data && data[key];
    if (!base || typeof base.plain_text !== "string" || !base.plain_text) return;
    if (!card.isConnected) return;
    const panel = buildCompare(base, card, key);
    const foot = card.querySelector(".snapshot-foot");
    if (foot) {
      foot.before(panel);
    } else {
      (card.querySelector(".bubble") || card).appendChild(panel);
    }
  } catch (error) {
    // No panel; the card stays as it is.
  }
}

function compareLabel(text) {
  const label = document.createElement("p");
  label.className = "compare-label";
  label.textContent = text;
  return label;
}

function buildCompare(base, card, key) {
  compareId += 1;
  const panel = document.createElement("section");
  panel.className = "compare";
  const body = document.createElement("div");
  body.className = "compare-body";
  body.id = `compare-${compareId}`;
  body.hidden = true;
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "compare-toggle";
  toggle.setAttribute("aria-controls", body.id);
  toggle.setAttribute("aria-expanded", "false");
  toggle.textContent = "Compare with a plain model";
  toggle.addEventListener("click", () => {
    const open = body.hidden;
    body.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.textContent = open ? "Hide the comparison" : "Compare with a plain model";
  });

  const grid = document.createElement("div");
  grid.className = "compare-grid";
  const plain = document.createElement("div");
  plain.className = "compare-block";
  plain.appendChild(compareLabel("Plain model, no tools"));
  if (base.plain_note) {
    const note = document.createElement("p");
    note.className = "compare-tag";
    note.textContent = String(base.plain_note);
    plain.appendChild(note);
  }
  const full = base.plain_text;
  const limit = COMPARE_PREVIEW_CHARS[key];
  const text = document.createElement("pre");
  text.className = "compare-text";
  plain.appendChild(text);
  if (limit && full.length > limit) {
    const more = document.createElement("button");
    more.type = "button";
    more.className = "compare-more";
    const show = (open) => {
      text.textContent = open ? full : full.slice(0, limit);
      more.setAttribute("aria-expanded", open ? "true" : "false");
      more.textContent = open ? "Show less" : "Show full answer";
    };
    more.addEventListener("click", () => show(more.getAttribute("aria-expanded") !== "true"));
    show(false);
    plain.appendChild(more);
  } else {
    text.textContent = full;
  }
  grid.appendChild(plain);

  const summary = card.querySelector(".summary");
  const chip = card.querySelector(".chip");
  if (summary && chip && summary.textContent.trim() && chip.textContent.trim()) {
    const app = document.createElement("div");
    app.className = "compare-block";
    app.appendChild(compareLabel("This app"));
    const line = document.createElement("p");
    line.className = "compare-summary";
    line.textContent = summary.textContent.trim();
    const worst = document.createElement("p");
    worst.className = "compare-worst";
    worst.append("Most serious result: ");
    const copy = document.createElement("span");
    copy.className = `chip ${chipClass(chip.textContent.trim())}`;
    copy.textContent = chip.textContent.trim();
    worst.appendChild(copy);
    app.append(line, worst);
    grid.appendChild(app);
  }

  const foot = document.createElement("p");
  foot.className = "compare-foot";
  const model = String(base.model || "a plain model");
  const when = base.run_utc ? `, run ${base.run_utc}` : "";
  foot.textContent = `Stored output from ${model}${when}. This is not a live call.`;
  body.append(grid, foot);
  panel.append(toggle, body);
  return panel;
}

loadMeta();
