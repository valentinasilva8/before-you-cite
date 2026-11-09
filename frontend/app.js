const log = document.querySelector("#log");
const tools = document.querySelector("#tools");
const form = document.querySelector("#composer");
const question = document.querySelector("#question");
const send = document.querySelector("#send");
const samples = document.querySelector("#samples");
let sessionId = null;

const labels = {
  sample1_turn1: "Sample 1, turn 1",
  sample1_turn2: "Sample 1, turn 2",
  sample2: "Sample 2",
  sample3: "Sample 3",
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

function addBubble(role, text) {
  const node = role === "assistant" ? renderAnswer(text) : document.createElement("div");
  if (role !== "assistant") {
    node.className = `bubble ${role}`;
    node.textContent = text;
  }
  log.appendChild(node);
  log.scrollTop = log.scrollHeight;
}

function renderAnswer(text) {
  const node = document.createElement("div");
  node.className = "bubble assistant";
  const lines = String(text || "").split("\n");
  const start = lines.findIndex((line) => line.trim().startsWith("| # | Verdict |"));
  if (start < 0) {
    node.textContent = text;
    return node;
  }
  let end = start;
  while (end < lines.length && lines[end].trim().startsWith("|")) {
    end += 1;
  }
  const before = lines.slice(0, start).join("\n").trim();
  const table = lines.slice(start, end).join("\n");
  const after = lines.slice(end).join("\n").trim();
  if (before) {
    const summary = document.createElement("p");
    summary.className = "summary";
    summary.textContent = before;
    node.appendChild(summary);
  }
  node.appendChild(renderTable(table));
  if (after) {
    const rest = document.createElement("div");
    rest.className = "after-table";
    rest.textContent = after;
    node.appendChild(rest);
  }
  return node;
}

function renderTable(markdown) {
  const table = document.createElement("table");
  table.className = "verdicts";
  for (const line of markdown.split("\n")) {
    if (!line.trim().startsWith("|")) {
      continue;
    }
    const cells = line.split("|").slice(1, -1).map((cell) => cell.trim());
    if (!cells.length || cells.every((cell) => /^:?-+:?$/.test(cell))) {
      continue;
    }
    const header = cells[1] === "Verdict";
    const row = document.createElement("tr");
    cells.forEach((value, index) => {
      const el = document.createElement(header ? "th" : "td");
      if (!header && index === 1) {
        const chip = document.createElement("span");
        chip.className = `chip ${chipClass(value)}`;
        chip.textContent = value;
        el.appendChild(chip);
      } else {
        el.textContent = value;
      }
      row.appendChild(el);
    });
    table.appendChild(row);
  }
  return table;
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
    document.querySelector("#commit").textContent = body.commit_short || body.commit;
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
  question.value = "";
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
    addBubble("assistant", body.response || "No response.");
    showTools(body.tool_calls || []);
  } catch (error) {
    addBubble("assistant", "The audit request did not reach the server. Check the connection and try again.");
  } finally {
    clearPending();
    send.disabled = false;
  }
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
