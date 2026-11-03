/* Incident triage agent — operator UI (no build step) */
(() => {
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
));
const num = (n) => Number(n || 0).toLocaleString();
const human = (s) => (s || "").replaceAll("_", " ");
const argStr = (a) => Object.entries(a || {})
  .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
  .join(", ");
const withoutKeys = (o, ks) => Object.fromEntries(
  Object.entries(o || {}).filter(([k]) => !ks.includes(k))
);
const TERMINAL = ["completed", "failed", "cancelled"];
const RESUMABLE = ["paused", "interrupted", "failed", "needs_attention"];

let runId = null;
let es = null;
let pendingKey = null;
let refreshTimer = null;
let cards = {};
let lastStep = null;
let sseRetry = 0;
let sseTimer = null;
let streamCursor = 0;

const store = {
  get: (s, k) => { try { return s.getItem(k) || ""; } catch { return ""; } },
  set: (s, k, v) => { try { s.setItem(k, v); } catch { /* private mode */ } },
};
const token = () => store.get(sessionStorage, "apiToken");

function showBanner(kind, message, { actionLabel, onAction } = {}) {
  const b = $("#banner");
  b.className = `banner visible ${kind}`;
  b.innerHTML = `<span>${esc(message)}</span>`;
  if (actionLabel && onAction) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = actionLabel;
    btn.onclick = onAction;
    b.appendChild(btn);
  }
}
function hideBanner() {
  const b = $("#banner");
  b.className = "banner";
  b.innerHTML = "";
}

async function api(path, opts = {}, retried = false) {
  const headers = {
    "content-type": "application/json",
    "x-operator": $("#operator").value.trim(),
  };
  if (token()) headers.authorization = `Bearer ${token()}`;
  const r = await fetch(path, { ...opts, headers });
  if (r.status === 401 && !retried) {
    const t = prompt("This server requires an API token. Paste it to continue:");
    if (t) {
      store.set(sessionStorage, "apiToken", t.trim());
      return api(path, opts, true);
    }
  }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const detail = typeof j.detail === "string" ? j.detail : `${r.status} ${r.statusText}`;
    throw new Error(detail);
  }
  return j;
}
const post = (p, body) => api(p, { method: "POST", body: JSON.stringify(body || {}) });

async function init() {
  $("#operator").value = store.get(localStorage, "operator");
  $("#operator").onchange = () => store.set(localStorage, "operator", $("#operator").value.trim());
  $("#ctxClose").onclick = () => $("#ctxDlg").close();

  try {
    const h = await api("/api/health");
    const mode = $("#mode");
    if (h.llm.provider === "scripted") {
      mode.innerHTML = `<span class="dot"></span>Offline demo policy — set an API key for a live model`;
      mode.classList.add("offline");
    } else {
      mode.innerHTML = `<span class="dot"></span>Model: ${esc(h.llm.model)}`;
      mode.classList.remove("offline");
    }
    const sc = await api("/api/scenarios");
    $("#scenario").innerHTML = sc.map((s) =>
      `<option value="${esc(s.id)}" title="${esc(s.description)}">${esc(s.title)}</option>`
    ).join("");
  } catch (e) {
    showBanner("err", `Cannot reach API: ${e.message}`, {
      actionLabel: "Retry",
      onAction: () => { hideBanner(); init(); },
    });
  }

  $("#startBtn").onclick = async () => {
    $("#startBtn").disabled = true;
    try {
      const r = await post("/api/runs", { scenario_id: $("#scenario").value });
      await loadRuns();
      select(r.run_id);
    } catch (e) {
      alert(e.message);
    } finally {
      $("#startBtn").disabled = false;
    }
  };

  await loadRuns();
  const fromHash = location.hash.slice(1);
  if (fromHash) select(fromHash);
  setInterval(loadRuns, 4000);
}

async function loadRuns() {
  const list = $("#runList");
  if (!list.children.length) {
    list.innerHTML = `<li class="skeleton" aria-hidden="true"></li>
      <li class="skeleton" aria-hidden="true"></li>`;
  }
  try {
    const runs = await api("/api/runs");
    if (!runs.length) {
      list.innerHTML = `<li class="small" style="padding:12px;cursor:default">No runs yet. Pick a scenario and start triage.</li>`;
      return;
    }
    list.innerHTML = runs.map((r) => `<li data-id="${esc(r.id)}" class="${r.id === runId ? "sel" : ""}" tabindex="0" role="button" aria-label="Open run ${esc(r.title)}">
      <div class="rl-title">${esc(r.title)}</div>
      <div class="rl-sub"><span class="status ${esc(r.status)}">${esc(human(r.status))}</span><span class="rid">${esc(r.id)}</span></div>
    </li>`).join("");
    list.querySelectorAll("li[data-id]").forEach((li) => {
      li.onclick = () => select(li.dataset.id);
      li.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(li.dataset.id); } };
    });
  } catch (e) {
    list.innerHTML = `<li class="small" style="padding:12px;color:var(--danger);cursor:default">Failed to load runs: ${esc(e.message)}</li>`;
  }
}

function select(id) {
  runId = id;
  history.replaceState(null, "", "#" + id);
  pendingKey = null;
  cards = {};
  lastStep = null;
  streamCursor = 0;
  sseRetry = 0;
  document.querySelectorAll("#runList li").forEach((li) => li.classList.toggle("sel", li.dataset.id === id));
  $("#trace").innerHTML = `<div class="loading-inline"><span class="spinner" aria-hidden="true"></span> Connecting to live event stream…</div>`;
  $("#side").innerHTML = "";
  delete $("#side").dataset.run;
  $("#traceHead").innerHTML = `<p class="empty-state"><strong>Loading run</strong>Fetching state for ${esc(id)}…</p>`;
  connectStream(id);
  refresh();
}

function connectStream(id) {
  if (es) { try { es.close(); } catch { /* */ } es = null; }
  clearTimeout(sseTimer);
  const q = new URLSearchParams();
  if (token()) q.set("token", token());
  if (streamCursor > 0) q.set("after", String(streamCursor));
  const qs = q.toString() ? `?${q}` : "";
  es = new EventSource(`/api/runs/${encodeURIComponent(id)}/stream${qs}`);
  const mode = $("#mode");

  es.onopen = () => {
    sseRetry = 0;
    mode.classList.remove("disconnected");
    hideBanner();
    const loading = $("#trace .loading-inline");
    if (loading) loading.remove();
  };

  es.onmessage = (e) => {
    try {
      const ev = JSON.parse(e.data);
      if (e.lastEventId) streamCursor = Math.max(streamCursor, Number(e.lastEventId) || 0);
      else if (ev.seq) streamCursor = Math.max(streamCursor, ev.seq);
      if (ev.run_id === runId) {
        render(ev);
        scheduleRefresh();
      }
    } catch (err) {
      console.warn("bad SSE frame", err);
    }
  };

  es.addEventListener("end", () => {
    try { es.close(); } catch { /* */ }
  });

  es.onerror = () => {
    try { es.close(); } catch { /* */ }
    es = null;
    mode.classList.add("disconnected");
    const delay = Math.min(1000 * (2 ** sseRetry), 15000);
    sseRetry += 1;
    showBanner("warn", `Live stream disconnected. Reconnecting in ${Math.round(delay / 1000)}s…`, {
      actionLabel: "Reconnect now",
      onAction: () => { hideBanner(); connectStream(id); },
    });
    sseTimer = setTimeout(() => {
      if (runId === id) connectStream(id);
    }, delay);
  };
}

function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(refresh, 200);
}

async function refresh() {
  if (!runId) return;
  const id = runId;
  try {
    const s = await api(`/api/runs/${encodeURIComponent(id)}`);
    if (id !== runId) return;
    $("#traceHead").innerHTML = `<h1>${esc(s.title)}</h1><p>${esc(s.task)}</p>`;
    renderSide(s);
  } catch (e) {
    $("#traceHead").innerHTML = `<div class="error-state" role="alert">${esc(e.message)}</div>`;
  }
}

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

function add(step, inner) {
  const col = $("#traceCol");
  const nearBottom = col.scrollHeight - col.scrollTop - col.clientHeight < 160;
  const node = el(`<div class="ev"><div class="gut">${step ? `<span>${step}</span>` : ""}</div><div class="body">${inner}</div></div>`);
  $("#trace").appendChild(node);
  if (nearBottom) col.scrollTop = col.scrollHeight;
  return node;
}

function stepLabel(p) {
  const s = p && p.step ? p.step : null;
  if (s === lastStep) return "";
  lastStep = s;
  return s ? `s${s}` : "";
}
const note = (p, html) => add(stepLabel(p), `<div class="note">${html}</div>`);

function toolCard(p) {
  const kind = p.kind === "write" ? "write" : "";
  const node = add(stepLabel(p), `<div class="tool ${kind}"><div class="tool-head"><span class="name">${esc(p.name)}</span>
    <span class="args" title="${esc(argStr(p.args))}">${esc(argStr(p.args))}</span>
    <span class="tag ${p.kind === "write" ? "wait" : ""}">${p.kind === "write" ? "needs approval" : "running"}</span></div><div class="extra"></div></div>`);
  cards[p.id] = node;
  return node;
}

function render(ev) {
  const p = ev.payload || {};
  switch (ev.type) {
    case "run.created":
      lastStep = null;
      note(p, `Run started with <b>${esc(p.model)}</b>`);
      break;
    case "memory.recalled":
      note(p, `Recalled ${p.memories.length} past incident(s) for this service from long-term memory`);
      break;
    case "memory.saved":
      note(p, "Saved a short, redacted summary of this incident to long-term memory");
      break;
    case "run.status":
      loadRuns();
      note(p, `Status: <b>${esc(human(p.status))}</b>${p.reason ? `. ${esc(p.reason)}` : ""}`);
      break;
    case "operator.control":
      note(p, `Operator asked to <b>${esc(p.action)}</b>`);
      break;
    case "llm.call": {
      const c = p.context || {};
      add(stepLabel(p), `<div class="telemetry"><span>${num(p.input_tokens)} tokens in</span><span>${num(p.output_tokens)} out</span>
        <span>${num(p.latency_ms)} ms</span><span>$${(p.cost_usd || 0).toFixed(4)}</span>
        <span>context ${num(c.total_tokens)} of ${num(c.budget)}</span>${c.dropped_groups ? `<span>${c.dropped_groups} old steps compacted</span>` : ""}</div>`);
      break;
    }
    case "llm.retry":
      note(p, `Model call failed (${esc(p.error)}). Retrying in ${p.retry_in_s}s.`);
      break;
    case "agent.message":
      add(stepLabel(p), `<div class="thought">${esc(p.text)}</div>`);
      break;
    case "tool.call":
      toolCard(p);
      break;
    case "tool.retry": {
      const c = cards[p.id];
      if (c) c.querySelector(".extra").insertAdjacentHTML("beforeend",
        `<div class="retry">Attempt ${p.attempt} failed: ${esc(p.error)}. Retrying in ${p.retry_in_s}s.</div>`);
      break;
    }
    case "tool.result": {
      const c = cards[p.id] || toolCard({ ...p, args: {}, kind: "read" });
      const tag = c.querySelector(".tag");
      tag.className = "tag " + (p.is_error ? "err" : "ok");
      tag.textContent = (p.is_error ? "error" : "ok")
        + (p.duration_ms != null ? `, ${p.duration_ms} ms` : "")
        + (p.attempts > 1 ? `, ${p.attempts} tries` : "");
      const trunc = p.truncated ? `, ${num(p.truncated.omitted_chars)} chars trimmed before the model saw it` : "";
      c.querySelector(".extra").insertAdjacentHTML("beforeend",
        `<details ${p.is_error ? "open" : ""}><summary>Output (${num(p.content.length)} chars${trunc})</summary><pre class="out">${esc(p.content)}</pre></details>`);
      break;
    }
    case "memory.update":
      note(p, `Updated working memory: ${esc((p.changed || []).join(", ") || "nothing")}`);
      break;
    case "context.compacted":
      note(p, `Compacted ${p.dropped_groups} oldest step(s) out of the transcript to stay under ${num(p.budget)} tokens. The action log keeps their outcomes.`);
      break;
    case "policy.blocked":
      add(stepLabel(p), `<div class="blocked">Blocked <code>${esc(p.tool)}</code>: confidence ${p.confidence} is below the ${p.min_confidence} minimum, so it went back to the agent instead of to you.</div>`);
      break;
    case "approval.requested": {
      const c = cards[p.tool_call_id];
      if (c) { const t = c.querySelector(".tag"); t.className = "tag wait"; t.textContent = "waiting for you"; }
      add(stepLabel(p), `<div class="gate"><b>Waiting for your approval</b><br><code>${esc(p.tool)}(${esc(argStr(withoutKeys(p.args, ["reason", "confidence"])))})</code></div>`);
      break;
    }
    case "approval.decided":
      note(p, `<b>${esc(p.actor || "Operator")}</b> ${esc(p.decision)} ${esc(p.tool)}${p.edited ? " with edited arguments" : ""}${p.feedback ? `: “${esc(p.feedback)}”` : ""}`);
      break;
    case "input.requested":
      add(stepLabel(p), `<div class="gate"><b>The agent asks:</b> ${esc(p.question)}</div>`);
      break;
    case "operator.message":
      note(p, `${esc(p.actor || "Operator")} said: “${esc(p.text)}”${p.queued ? " (the agent reads it at its next step)" : ""}`);
      break;
    case "run.finished": {
      const r = p.result;
      add(stepLabel(p), `<div class="outcome ${r.resolved ? "" : "bad"}"><b>${r.resolved ? "Resolved" : "Not resolved"}.</b> ${esc(r.summary)}</div>`);
      break;
    }
    default:
      note(p, esc(ev.type));
  }
}

function renderSide(s) {
  const side = $("#side");
  if (side.dataset.run !== s.run_id) {
    side.dataset.run = s.run_id;
    side.innerHTML = `<section id="sCtl"></section><section id="sPending"></section>
      <section id="sCompose"><h2 class="section-label">Message the agent</h2>
        <div class="row"><input id="opMsg" placeholder="Add context or correct its course" aria-label="Message to the agent"><button id="opSend" type="button">Send</button></div>
        <p class="reason">The agent reads it at its next step.</p></section>
      <section id="sResult"></section><section id="sPlan"></section><section id="sHyp"></section>
      <section id="sTel"></section><section id="sMem"></section>`;
    $("#opSend").onclick = sendMsg;
    $("#opMsg").onkeydown = (e) => { if (e.key === "Enter") sendMsg(); };
  }

  $("#sCtl").innerHTML = `<div class="status ${esc(s.status)}" style="font-size:14px">${esc(human(s.status))}</div>
    ${s.status_reason ? `<p class="reason">${esc(s.status_reason)}</p>` : ""}
    <div class="controls">
      <button type="button" data-a="pause" ${s.active && s.status === "running" ? "" : "disabled"}>Pause</button>
      <button type="button" data-a="resume" ${RESUMABLE.includes(s.status) ? "" : "disabled"}>Resume</button>
      <button type="button" data-a="cancel" class="btn-danger" ${TERMINAL.includes(s.status) ? "disabled" : ""}>Cancel run</button>
      <button type="button" data-a="context">Inspect context</button>
    </div>`;
  $("#sCtl").querySelectorAll("button[data-a]").forEach((b) => { b.onclick = () => control(b.dataset.a); });

  const p = s.pending;
  const key = p ? `${p.tool_call_id}:${s.status}` : "";
  if (key !== pendingKey) {
    pendingKey = key;
    if (p && s.status === "awaiting_approval") {
      const conf = Math.round((p.args.confidence || 0) * 100);
      $("#sPending").innerHTML = `<div class="approval" role="region" aria-label="Approval required">
        <h2>Approve a production change</h2>
        <p style="margin:0 0 6px">The agent wants to run <code>${esc(p.tool)}</code> on <b>${esc(p.args.service)}</b>.</p>
        <p class="small" style="margin:0 0 8px">${esc(p.args.reason)}</p>
        <div class="small">Agent confidence: ${conf}%</div><div class="meter" role="meter" aria-valuenow="${conf}" aria-valuemin="0" aria-valuemax="100"><i style="width:${conf}%"></i></div>
        <label class="small" for="apArgs">Arguments (edit before approving if needed)</label>
        <textarea id="apArgs" spellcheck="false">${esc(JSON.stringify(p.args, null, 2))}</textarea>
        <button class="btn-approve" id="apOk" type="button">Approve and run</button>
        <div class="row" style="margin-top:10px">
          <input id="apFb" placeholder="Reason for rejecting (sent to the agent)" aria-label="Rejection feedback">
          <button class="btn-danger" id="apNo" type="button">Reject</button>
        </div></div>`;
      $("#apOk").onclick = approve;
      $("#apNo").onclick = reject;
    } else if (p && s.status === "awaiting_input") {
      $("#sPending").innerHTML = `<div class="approval" role="region" aria-label="Input required">
        <h2>The agent needs an answer</h2>
        <p style="margin:0 0 10px">${esc(p.question)}</p>
        <div class="row"><input id="ansTxt" placeholder="Your answer" aria-label="Answer">
        <button class="btn-approve" id="ansOk" type="button">Send answer</button></div></div>`;
      $("#ansOk").onclick = () => act(() => post(`/api/runs/${runId}/message`, { text: $("#ansTxt").value }));
    } else {
      $("#sPending").innerHTML = "";
    }
  }
  $("#sCompose").style.display = TERMINAL.includes(s.status) || s.status === "awaiting_input" ? "none" : "";

  const r = s.result;
  $("#sResult").innerHTML = r ? `<div class="report"><h2 class="section-label">Incident report</h2>
    <div class="outcome ${r.resolved ? "" : "bad"}"><b>${r.resolved ? "Resolved" : "Not resolved"}</b><p>${esc(r.summary)}</p></div>
    <p><b>Root cause.</b> ${esc(r.root_cause)}</p>${r.fix_applied ? `<p><b>Fix.</b> <code>${esc(r.fix_applied)}</code></p>` : ""}
    ${r.follow_ups?.length ? `<b>Follow-ups</b><ul>${r.follow_ups.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}
    <p class="reason">Simulator check: ${r.sim_resolved ? "the incident really is fixed." : "the incident is NOT actually fixed."}</p></div>` : "";

  $("#sPlan").innerHTML = `<h2 class="section-label">Plan</h2>` + (s.plan.length
    ? `<ol class="plan">${s.plan.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>`
    : '<p class="small">No plan yet.</p>');
  $("#sHyp").innerHTML = `<h2 class="section-label">Hypotheses</h2>` + (s.hypotheses.length
    ? s.hypotheses.map((h) => `<div class="hyp ${esc(h.status)}"><span class="st">${esc(h.status)}</span><span class="t">${esc(h.text)}</span>${h.evidence ? `<div class="ev-text">${esc(h.evidence)}</div>` : ""}</div>`).join("")
    : '<p class="small">None yet.</p>');

  const u = s.usage, c = s.last_context;
  let ctx = "";
  if (c) {
    const w = (v) => Math.min(100, (v / c.budget) * 100).toFixed(1);
    ctx = `<h2 class="section-label" style="margin-top:14px">Last context window</h2>
      <div class="ctxbar" role="img" aria-label="${num(c.total_tokens)} of ${num(c.budget)} tokens">
        <i style="width:${w(c.system_tokens + c.tools_tokens)}%;background:var(--text-tertiary)"></i>
        <i style="width:${w(c.memory_tokens)}%;background:var(--accent)"></i>
        <i style="width:${w(c.history_tokens)}%;background:var(--warning)"></i></div>
      <div class="legend"><span style="--c:var(--text-tertiary)">System and tools</span><span style="--c:var(--accent)">Working memory</span><span style="--c:var(--warning)">Transcript</span></div>
      <p class="reason">${num(c.total_tokens)} of ${num(c.budget)} estimated tokens. ${c.shrunk_messages} old outputs shortened, ${c.dropped_groups} old steps dropped.</p>`;
  }
  $("#sTel").innerHTML = `<h2 class="section-label">Telemetry</h2><dl class="kv">
    <dt>Steps</dt><dd>${s.step} / ${s.max_steps}</dd>
    <dt>Model calls</dt><dd>${u.llm_calls}</dd>
    <dt>Tokens in / out</dt><dd>${num(u.input_tokens)} / ${num(u.output_tokens)}</dd>
    <dt>Estimated cost</dt><dd>$${u.cost_usd.toFixed(4)}</dd>
    <dt>Model time</dt><dd>${(u.llm_ms / 1000).toFixed(1)} s</dd>
    <dt>Tool calls</dt><dd>${u.tool_calls}</dd>
    <dt>Retries / errors</dt><dd>${u.tool_retries} / ${u.tool_errors}</dd>
    <dt>Checkpoint</dt><dd>v${s.checkpoint_version}</dd></dl>${ctx}`;

  $("#sMem").innerHTML = s.recalled_memories?.length
    ? `<h2 class="section-label">From past incidents</h2>${s.recalled_memories.map((m) =>
      `<div class="hyp"><div class="ev-text">${esc(m.date)}, ${m.age_days} days ago</div>${esc(m.root_cause)}</div>`).join("")}`
    : "";
}

async function act(fn) {
  try {
    await fn();
    pendingKey = null;
    await refresh();
    loadRuns();
  } catch (e) {
    alert(e.message);
  }
}

async function approve() {
  if (!$("#operator").value.trim()) {
    $("#operator").focus();
    return alert("Enter your name first: approvals are recorded in the audit log.");
  }
  let args;
  try { args = JSON.parse($("#apArgs").value); }
  catch { return alert("The arguments must be valid JSON."); }
  await act(() => post(`/api/runs/${runId}/approve`, { args }));
}

const reject = () => act(() => post(`/api/runs/${runId}/reject`, { feedback: $("#apFb").value }));

async function sendMsg() {
  const t = $("#opMsg").value.trim();
  if (!t) return;
  await act(() => post(`/api/runs/${runId}/message`, { text: t }));
  $("#opMsg").value = "";
}

async function control(a) {
  if (a === "context") return showContext();
  if (a === "cancel" && !confirm("Cancel this run? It cannot be resumed afterwards.")) return;
  await act(() => post(`/api/runs/${runId}/${a}`));
}

async function showContext() {
  const c = await api(`/api/runs/${encodeURIComponent(runId)}/context`);
  const show = (m) => (m.role === "assistant"
    ? ((m.text ? m.text + "\n" : "") + (m.tool_calls || []).map((t) => `→ ${t.name}(${JSON.stringify(t.args)})`).join("\n"))
    : m.content);
  $("#ctxBody").innerHTML = `<p class="small" style="margin-top:0">Rebuilt from the latest checkpoint, exactly as it will be sent. About ${num(c.stats.total_tokens)} of ${num(c.stats.budget)} tokens.</p>
    <div class="msg"><div class="role">System prompt</div><pre class="out">${esc(c.system)}</pre></div>`
    + c.messages.map((m) => `<div class="msg"><div class="role">${esc(m.role === "tool" ? `Tool result: ${m.name}` : m.role === "assistant" ? "Agent" : "User")}</div><pre class="out">${esc(show(m))}</pre></div>`).join("");
  $("#ctxDlg").showModal();
}

document.addEventListener("DOMContentLoaded", init);
})();
