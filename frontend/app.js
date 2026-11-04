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
  const node = document.createElement("div");
  node.className = `bubble ${role}`;
  node.textContent = text;
  log.appendChild(node);
  log.scrollTop = log.scrollHeight;
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

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = question.value.trim();
  if (!message) return;
  addBubble("user", message);
  question.value = "";
  send.disabled = true;
  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    const body = await response.json();
    sessionId = body.session_id || sessionId;
    addBubble("assistant", body.response || "No response.");
    showTools(body.tool_calls || []);
  } catch (error) {
    addBubble("assistant", "The request failed before a response arrived.");
  } finally {
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
