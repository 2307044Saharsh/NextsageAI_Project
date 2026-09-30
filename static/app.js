let cases = [];
let selected = null;
let currentDiagnosis = null;
let currentValidation = null;
let dashboardSummary = null;
let spreadsheetRows = [];
let chatHistory = [];

const $ = (id) => document.getElementById(id);

const CONCEPT_ICONS = {
  VLAN: "🔀",
  Routing: "🛤️",
  Gateway: "🚪",
  DHCP: "📡",
  DNS: "🌐",
  ACL: "🛡️",
  NAT: "↔️",
  Interface: "🔌",
  Wireless: "📶",
};

const GREETINGS = [
  "Hey — I'm Sage. Ask me about any networking topic, not just the lab tickets.",
  "Paste symptoms, show output, or study questions — I'll show my reasoning step by step.",
];

async function get(path, options) {
  const response = await fetch(path, options);
  if (response.ok) return response.json();
  const body = await response.json().catch(() => ({}));
  throw Error(body.detail || "Something went wrong — try again?");
}

function toast(message) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  $("toastStack").append(node);
  setTimeout(() => node.remove(), 3200);
}

function conceptIcon(concept) {
  return CONCEPT_ICONS[concept] || "📋";
}

function setStatus(text) {
  const pill = $("liveStatus");
  if (pill?.lastChild) pill.lastChild.textContent = text;
}

async function loadAiStatus() {
  try {
    const status = await get("/api/ai/status");
    const label = status.active_backend === "fallback"
      ? "Rules fallback — Ollama/HF available for live AI"
      : `Live AI: ${status.active_backend}`;
    setStatus(label);
    const pill = $("liveStatus");
    if (pill) pill.title = status.note;
  } catch {
    setStatus("Ready when you are");
  }
}

function setStep(stepName) {
  const order = ["pick", "check", "diagnose", "review"];
  const activeIndex = order.indexOf(stepName);
  document.querySelectorAll(".step").forEach((step) => {
    const index = order.indexOf(step.dataset.step);
    step.classList.toggle("active", index === activeIndex);
    step.classList.toggle("done", index < activeIndex);
  });
}

function setButtonLoading(button, loading, loadingText) {
  if (!button) return;
  button.disabled = loading;
  button.classList.toggle("loading", loading);
  const label = button.querySelector(".btn-text");
  if (label) {
    if (!label.dataset.default) label.dataset.default = label.textContent;
    label.textContent = loading ? loadingText : label.dataset.default;
  }
}

function scrollThread() {
  const thread = $("thread");
  thread.scrollTop = thread.scrollHeight;
}

function clearThread(keepWelcome = true) {
  const thread = $("thread");
  thread.replaceChildren();
  if (keepWelcome) {
    addBubble(
      "sage",
      `<p>${GREETINGS[0]} ${GREETINGS[1]}</p>`,
      true,
    );
  }
}

function addBubble(kind, html, isHtml = false) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${kind}`;
  if (isHtml) bubble.innerHTML = html;
  else bubble.textContent = html;
  $("thread").append(bubble);
  scrollThread();
  return bubble;
}

function addUserAction(text) {
  addBubble("user", text);
}

function showTyping() {
  const bubble = document.createElement("div");
  bubble.className = "bubble sage typing";
  bubble.id = "typingIndicator";
  bubble.innerHTML = "<span></span><span></span><span></span>";
  $("thread").append(bubble);
  scrollThread();
  return bubble;
}

function hideTyping() {
  $("typingIndicator")?.remove();
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function updateChatModeLabel() {
  const label = $("chatModeLabel");
  if (!selected) {
    label.textContent = "Open discussion — ask about any scenario, not limited to the 32 tickets";
    $("includeCaseContext").checked = false;
    $("includeCaseContext").disabled = true;
    return;
  }
  $("includeCaseContext").disabled = false;
  const useContext = $("includeCaseContext").checked;
  label.textContent = useContext
    ? `Discussing freely · ${selected.case_id} context attached`
    : `Discussing freely · ${selected.case_id} open but context hidden`;
}

function metric(value, label) {
  const card = document.createElement("div");
  card.className = "metric";
  card.innerHTML = `<strong>${value}</strong><span>${label}</span>`;
  return card;
}

/* ==========================================================================
   VIEW SWITCHER (WORKSPACE vs DASHBOARD)
   ========================================================================== */
function switchView(viewName) {
  const isWorkspace = viewName === "workspace";
  $("workspaceView").hidden = !isWorkspace;
  $("dashboardView").hidden = isWorkspace;

  $("tabWorkspace").classList.toggle("active", isWorkspace);
  $("tabWorkspace").setAttribute("aria-selected", String(isWorkspace));
  $("tabDashboard").classList.toggle("active", !isWorkspace);
  $("tabDashboard").setAttribute("aria-selected", String(!isWorkspace));

  if (!isWorkspace) {
    refreshDashboard();
  }
}

/* ==========================================================================
   DYNAMIC CHARTS & DASHBOARD RENDERING
   ========================================================================== */
function renderConceptChart(byConcept, total) {
  const container = $("chartConcepts");
  container.replaceChildren();

  const sortedConcepts = Object.entries(byConcept).sort((a, b) => b[1] - a[1]);

  sortedConcepts.forEach(([concept, count]) => {
    const pct = total > 0 ? Math.round((count / total) * 100) : 0;
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <div class="bar-label" title="${concept}">${conceptIcon(concept)} ${concept}</div>
      <div class="bar-track">
        <div class="bar-fill concept-${concept.toLowerCase()}" style="width: ${pct}%"></div>
      </div>
      <div class="bar-val">${count} (${pct}%)</div>
    `;
    container.append(row);
  });
}

function renderAgreementChart(reviewStatus, total, agreementRate) {
  const container = $("chartAgreement");
  container.replaceChildren();

  const statuses = [
    { key: "Accepted", label: "Accepted", class: "status-accepted", desc: "AI diagnosis confirmed" },
    { key: "Edited", label: "Edited", class: "status-edited", desc: "Human corrected AI" },
    { key: "Rejected", label: "Rejected", class: "status-rejected", desc: "AI diagnosis denied" },
    { key: "Pending", label: "Pending", class: "status-pending", desc: "Awaiting human review" },
  ];

  statuses.forEach(({ key, label, class: cls, desc }) => {
    const count = reviewStatus[key] || 0;
    const pct = total > 0 ? Math.round((count / total) * 100) : 0;
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <div class="bar-label" title="${desc}">${label}</div>
      <div class="bar-track">
        <div class="bar-fill ${cls}" style="width: ${pct}%"></div>
      </div>
      <div class="bar-val">${count} (${pct}%)</div>
    `;
    container.append(row);
  });

  const summaryPill = document.createElement("div");
  summaryPill.style.marginTop = "12px";
  summaryPill.style.fontSize = "0.85rem";
  summaryPill.style.color = "var(--muted)";
  summaryPill.innerHTML = `💡 Overall AI-Human Agreement Rate: <strong style="color:var(--sage)">${agreementRate}%</strong> across reviewed tickets.`;
  container.append(summaryPill);
}

function renderSeverityChart(bySeverity, total) {
  const container = $("chartSeverity");
  container.replaceChildren();

  const sevs = ["Critical", "High", "Medium", "Low"];
  sevs.forEach((sev) => {
    const count = bySeverity[sev] || 0;
    const pct = total > 0 ? Math.round((count / total) * 100) : 0;
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <div class="bar-label">${sev}</div>
      <div class="bar-track">
        <div class="bar-fill sev-${sev.toLowerCase()}" style="width: ${pct}%"></div>
      </div>
      <div class="bar-val">${count} (${pct}%)</div>
    `;
    container.append(row);
  });
}

function renderCorrectionsChart(correctionStatus, totalCorrections) {
  const container = $("chartCorrections");
  container.replaceChildren();

  const total = totalCorrections || Object.values(correctionStatus || {}).reduce((a, b) => a + b, 0);

  if (total === 0) {
    container.innerHTML = `<p class="body-copy" style="color:var(--muted)">No responsible AI corrections logged yet.</p>`;
    return;
  }

  const items = [
    { label: "Edited Diagnoses", count: correctionStatus.Edited || 0, cls: "status-edited" },
    { label: "Rejected Diagnoses", count: correctionStatus.Rejected || 0, cls: "status-rejected" },
  ];

  items.forEach(({ label, count, cls }) => {
    const pct = total > 0 ? Math.round((count / total) * 100) : 0;
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <div class="bar-label">${label}</div>
      <div class="bar-track">
        <div class="bar-fill ${cls}" style="width: ${pct}%"></div>
      </div>
      <div class="bar-val">${count} (${pct}%)</div>
    `;
    container.append(row);
  });

  const note = document.createElement("p");
  note.style.marginTop = "12px";
  note.style.fontSize = "0.82rem";
  note.style.color = "var(--muted)";
  note.innerHTML = `<em>Audit Log: 5 reference cases documented in <code>data/responsible_ai_log.csv</code> where human oversight prevented configuration mistakes.</em>`;
  container.append(note);
}

function renderDashboard(summary) {
  dashboardSummary = summary;
  const metrics = $("metrics");
  metrics.replaceChildren(
    metric(summary.total_cases, "lab tickets"),
    metric(`${summary.reviewed_cases}/${summary.total_cases}`, "reviewed by humans"),
    metric(`${summary.agreement_rate}%`, "AI agreement rate"),
    metric(summary.review_status.Pending, "still waiting on you"),
  );

  const dashMetrics = $("dashMetrics");
  if (dashMetrics) {
    dashMetrics.replaceChildren(
      metric(summary.total_cases, "Total Lab Cases"),
      metric(`${summary.reviewed_cases}`, "Human Verified"),
      metric(`${summary.agreement_rate}%`, "Agreement Rate"),
      metric(summary.review_status.Pending, "Pending Reviews"),
      metric(summary.responsible_ai_corrections || 5, "Responsible AI Corrections"),
    );
  }

  renderConceptChart(summary.by_concept, summary.total_cases);
  renderAgreementChart(summary.review_status, summary.total_cases, summary.agreement_rate);
  renderSeverityChart(summary.by_severity, summary.total_cases);
  renderCorrectionsChart(summary.correction_status, summary.responsible_ai_corrections);
}

/* ==========================================================================
   LIVE SPREADSHEET TABLE LOGIC
   ========================================================================== */
async function loadSpreadsheetData() {
  try {
    spreadsheetRows = await get("/api/spreadsheet");
    filterAndRenderSpreadsheet();
  } catch (error) {
    console.error("Failed to load spreadsheet data:", error);
  }
}

function filterAndRenderSpreadsheet() {
  const query = $("spreadSearch") ? $("spreadSearch").value.trim().toLowerCase() : "";
  const conceptFilter = $("spreadConceptFilter") ? $("spreadConceptFilter").value : "";
  const statusFilter = $("spreadStatusFilter") ? $("spreadStatusFilter").value : "";
  const severityFilter = $("spreadSeverityFilter") ? $("spreadSeverityFilter").value : "";

  const filtered = spreadsheetRows.filter((row) => {
    if (conceptFilter && row.concept !== conceptFilter) return false;
    if (statusFilter && row.status !== statusFilter) return false;
    if (severityFilter && row.severity !== severityFilter) return false;
    if (query) {
      const haystack = `${row.case_id} ${row.title} ${row.symptom} ${row.expected_fault} ${row.ai_diagnosis} ${row.reviewer_name} ${row.notes}`.toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    return true;
  });

  const countBadge = $("tableRowCount");
  if (countBadge) {
    countBadge.textContent = `Showing ${filtered.length} of ${spreadsheetRows.length} cases`;
  }

  const tbody = $("spreadsheetBody");
  if (!tbody) return;
  tbody.replaceChildren();

  if (!filtered.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="10" style="text-align:center;padding:32px;color:var(--muted)">No cases match the active spreadsheet filters.</td>`;
    tbody.append(tr);
    return;
  }

  filtered.forEach((row) => {
    const tr = document.createElement("tr");
    const statusClass = (row.status || "Pending").toLowerCase();

    tr.innerHTML = `
      <td class="mono"><strong>${row.case_id}</strong></td>
      <td><span class="tag">${conceptIcon(row.concept)} ${row.concept}</span></td>
      <td><span class="tag">${row.osi_layer}</span></td>
      <td><span class="severity-chip ${row.severity.toLowerCase()}">${row.severity}</span></td>
      <td style="max-width:240px;font-size:0.83rem">${row.symptom}</td>
      <td style="max-width:200px;font-size:0.83rem;font-weight:500">${row.expected_fault}</td>
      <td style="max-width:200px;font-size:0.83rem;color:var(--sage)">${row.ai_diagnosis}</td>
      <td><span class="status-chip ${statusClass}">${row.status}</span></td>
      <td style="max-width:180px;font-size:0.8rem;color:var(--muted)">
        ${row.reviewer_name !== "—" ? `<strong>${row.reviewer_name}</strong><br>` : ""}
        ${row.notes !== "—" ? `<em>${row.notes}</em>` : "—"}
      </td>
      <td>
        <button type="button" class="btn-table-action" data-case="${row.case_id}">
          🛠️ Troubleshoot
        </button>
      </td>
    `;

    tr.querySelector(".btn-table-action")?.addEventListener("click", () => {
      switchView("workspace");
      selectCase(row.case_id);
    });

    tbody.append(tr);
  });
}

function exportSpreadsheetCsv() {
  if (!spreadsheetRows.length) {
    toast("No spreadsheet data available to export.");
    return;
  }

  const headers = [
    "case_id",
    "title",
    "concept",
    "osi_layer",
    "severity",
    "symptom",
    "expected_fault",
    "ai_diagnosis",
    "status",
    "reviewer_name",
    "reviewed_at",
    "notes",
  ];

  const csvRows = [headers.join(",")];

  spreadsheetRows.forEach((row) => {
    const values = headers.map((field) => {
      const val = row[field] ? String(row[field]).replace(/"/g, '""') : "";
      return `"${val}"`;
    });
    csvRows.push(values.join(","));
  });

  const blob = new Blob([csvRows.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `netsage_troubleshooting_spreadsheet_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  toast("Spreadsheet CSV exported successfully!");
}

async function refreshDashboard() {
  try {
    const summary = await get("/api/dashboard");
    renderDashboard(summary);
    await loadSpreadsheetData();
    toast("Dashboard & Spreadsheet updated with live data");
  } catch (error) {
    console.error("Dashboard refresh error:", error);
  }
}

/* ==========================================================================
   WORKSPACE TICKET LIST & CHAT LOGIC
   ========================================================================== */
function renderCaseList(filter = "") {
  const query = filter.trim().toLowerCase();
  const container = $("caseList");
  container.replaceChildren();

  const filtered = cases.filter((caseItem) => {
    if (!query) return true;
    const haystack = `${caseItem.case_id} ${caseItem.title} ${caseItem.symptom} ${caseItem.concept}`.toLowerCase();
    return haystack.includes(query);
  });

  if (!filtered.length) {
    const empty = document.createElement("p");
    empty.className = "body-copy";
    empty.textContent = "No tickets match that search — try VLAN, DHCP, or routing.";
    container.append(empty);
    return;
  }

  filtered.forEach((caseItem) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "case-card";
    button.dataset.id = caseItem.case_id;
    if (selected?.case_id === caseItem.case_id) button.classList.add("active");

    button.innerHTML = `
      <div class="case-card-top">
        <span class="case-card-id">${caseItem.case_id}</span>
        <span class="tag">${conceptIcon(caseItem.concept)} ${caseItem.concept}</span>
      </div>
      <div class="case-card-title">${caseItem.title}</div>
      <div class="case-card-snippet">${caseItem.symptom}</div>
      <div class="case-card-tags">
        <span class="tag">${caseItem.severity}</span>
        <span class="tag">${caseItem.osi_layer}</span>
      </div>
    `;

    button.addEventListener("click", () => selectCase(caseItem.case_id));
    container.append(button);
  });
}

function renderChatResponse(response) {
  const reasoning = response.reasoning.length
    ? `<details class="reasoning-block" open><summary>How I'm thinking about this</summary><ol>${response.reasoning.map((step) => `<li>${step}</li>`).join("")}</ol></details>`
    : "";

  const layers = response.likely_layers.length
    ? `<p style="margin-top:8px;font-size:0.85rem"><strong>Layers in play:</strong> ${response.likely_layers.join(" · ")}</p>`
    : "";

  const commands = response.suggested_commands.length
    ? `<div class="command-chips">${response.suggested_commands.map((cmd) => `<span class="command-chip">${cmd}</span>`).join("")}</div>`
    : "";

  const followUps = response.follow_up_questions.length
    ? `<div class="follow-up"><strong>Quick questions for you:</strong><ul>${response.follow_up_questions.map((q) => `<li>${q}</li>`).join("")}</ul></div>`
    : "";

  const contextNote = response.case_context_used
    ? `<p style="font-size:0.8rem;color:var(--muted)">Used the open lab ticket as background context.</p>`
    : "";

  return `
    <p>${response.reply}</p>
    ${reasoning}
    ${layers}
    ${commands ? `<p style="margin-top:8px;font-size:0.85rem"><strong>Commands I'd try:</strong></p>${commands}` : ""}
    ${followUps}
    ${contextNote}
    <p style="margin-top:8px;font-size:0.8rem;color:var(--muted)"><em>${response.safety_note}</em> · via ${response.source}</p>
  `;
}

function openChatMode() {
  selected = null;
  chatHistory = [];
  currentDiagnosis = null;
  currentValidation = null;

  renderCaseList($("caseSearch").value);
  document.querySelectorAll(".case-card").forEach((card) => card.classList.remove("active"));

  $("caseId").textContent = "Open chat";
  $("severityChip").textContent = "Free discussion";
  $("severityChip").className = "severity-chip";
  $("conceptChip").textContent = "Any topic";
  $("title").textContent = "Ask Sage anything";
  $("symptom").textContent = "Not limited to the 32 lab tickets — troubleshooting, concepts, design questions, or paste your own show output.";
  $("topology").textContent = "No ticket selected. Describe your own topology or scenario in the chat.";
  $("outputs").textContent = "# Paste show command output in the chat box below";

  $("validate").disabled = true;
  $("diagnose").disabled = true;
  $("review").hidden = true;

  clearThread();
  updateChatModeLabel();
  setStatus("Open discussion");
  toast("Open chat — ask about anything");
}

function selectCase(caseId) {
  selected = cases.find((caseItem) => caseItem.case_id === caseId);
  if (!selected) return;

  renderCaseList($("caseSearch").value);
  setStep("pick");

  $("caseId").textContent = selected.case_id;
  $("severityChip").textContent = selected.severity;
  $("severityChip").className = `severity-chip ${selected.severity.toLowerCase()}`;
  $("conceptChip").textContent = `${conceptIcon(selected.concept)} ${selected.concept}`;
  $("title").textContent = selected.title;
  $("symptom").textContent = selected.symptom;
  $("topology").textContent = selected.topology_note || "No topology notes for this ticket.";
  $("outputs").textContent = selected.show_outputs;

  currentDiagnosis = null;
  currentValidation = null;
  $("diagnose").disabled = true;
  $("validate").disabled = false;
  $("review").hidden = true;
  $("correction").value = "";
  $("reviewMessage").textContent = "";

  addBubble("system", `Switched to ${selected.case_id} — ${selected.title}`);
  addUserAction(`Let's look at ${selected.case_id}: "${selected.symptom}"`);
  addBubble(
    "sage",
    `<p>Got it. Topology and show output are on the left. Use the buttons for structured evidence checks, or just <strong>type a question below</strong> — you can ask about this ticket or anything else.</p>`,
    true,
  );

  updateChatModeLabel();
  setStatus(`Working on ${selected.case_id}`);
  toast(`Opened ${selected.title}`);
}

function renderValidationFindings(validation) {
  if (!validation.findings.length) {
    return `<p>I didn't spot a clear pattern in the evidence yet. That's okay — sometimes you need one more <code>show</code> command. Want me to take a broader guess anyway?</p>`;
  }

  const cards = validation.findings
    .map(
      (finding) => `
        <div class="finding-card ${finding.severity.toLowerCase()}">
          <strong>${finding.root_cause}</strong>
          <p style="margin:6px 0 0;color:var(--muted);font-size:0.85rem">${finding.evidence}</p>
          <p style="margin:6px 0 0;font-size:0.82rem">Try next: <code>${finding.next_command}</code></p>
        </div>
      `,
    )
    .join("");

  const opener =
    validation.findings.length === 1
      ? "Here's what jumped out at me from the show output:"
      : `I found ${validation.findings.length} things worth looking at:`;

  return `<p>${opener}</p>${cards}<p style="margin-top:10px;font-size:0.85rem;color:var(--muted)">${validation.safety_note}</p>`;
}

function renderDiagnosisMessage(diagnosis) {
  const confidenceLabel = {
    high: "pretty confident",
    medium: "moderately confident",
    low: "still uncertain",
  }[diagnosis.confidence] || diagnosis.confidence;

  const alternatives = diagnosis.alternative_hypotheses.length
    ? `<p style="margin-top:10px"><strong>Could also be:</strong></p><ul>${diagnosis.alternative_hypotheses.map((item) => `<li>${item}</li>`).join("")}</ul>`
    : "";

  return `
    <span class="confidence-pill">${confidenceLabel} · ${diagnosis.source}</span>
    <h4>My best read: ${diagnosis.root_cause}</h4>
    <p>OSI layer: <strong>${diagnosis.osi_layer}</strong></p>
    <p><strong>What I used from the evidence:</strong></p>
    <ul>${diagnosis.evidence.map((item) => `<li>${item}</li>`).join("")}</ul>
    <p>I'd run <code>${diagnosis.next_command}</code> next before changing anything.</p>
    <p><strong>If a human approves a fix:</strong></p>
    <ol>${diagnosis.fix_steps.map((item) => `<li>${item}</li>`).join("")}</ol>
    ${alternatives}
    <p style="margin-top:10px;font-size:0.85rem;color:var(--muted)">After approval, verify with <code>${diagnosis.verification_command}</code> — expect: ${diagnosis.verification_expected_result}</p>
    <p style="margin-top:8px;font-size:0.85rem"><em>${diagnosis.safety_note}</em></p>
  `;
}

/* ==========================================================================
   APP INITIALIZATION & EVENT LISTENERS
   ========================================================================== */
async function load() {
  cases = await get("/api/cases");
  renderCaseList();
  renderDashboard(await get("/api/dashboard"));
  await loadSpreadsheetData();
  await loadAiStatus();
  openChatMode();

  // Tab View Switcher Listeners
  $("tabWorkspace")?.addEventListener("click", () => switchView("workspace"));
  $("tabDashboard")?.addEventListener("click", () => switchView("dashboard"));

  // Dashboard & Spreadsheet Controls
  $("btnRefreshDash")?.addEventListener("click", refreshDashboard);
  $("btnExportCsv")?.addEventListener("click", exportSpreadsheetCsv);
  $("spreadSearch")?.addEventListener("input", filterAndRenderSpreadsheet);
  $("spreadConceptFilter")?.addEventListener("change", filterAndRenderSpreadsheet);
  $("spreadStatusFilter")?.addEventListener("change", filterAndRenderSpreadsheet);
  $("spreadSeverityFilter")?.addEventListener("change", filterAndRenderSpreadsheet);

  $("caseSearch").addEventListener("input", (event) => {
    renderCaseList(event.target.value);
  });

  $("openChatMode").addEventListener("click", openChatMode);
  $("includeCaseContext").addEventListener("change", updateChatModeLabel);

  $("chatForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = $("chatInput").value.trim();
    if (!message) return;

    addUserAction(message);
    chatHistory.push({ role: "user", content: message });
    $("chatInput").value = "";
    $("sendChat").disabled = true;
    setStatus("Sage is reasoning…");
    showTyping();

    try {
      const response = await get("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          history: chatHistory.slice(0, -1),
          case_id: selected?.case_id ?? null,
          include_case_context: $("includeCaseContext").checked,
        }),
      });
      hideTyping();
      chatHistory.push({ role: "assistant", content: response.reply });
      addBubble("sage", renderChatResponse(response), true);
      setStatus("Ready for your next question");
      toast("Reply ready");
    } catch (error) {
      hideTyping();
      addBubble("sage", `<p>Sorry, I couldn't process that: ${error.message}</p>`, true);
      setStatus("Chat error");
    } finally {
      $("sendChat").disabled = false;
      $("chatInput").focus();
    }
  });
}

$("validate").addEventListener("click", async () => {
  if (!selected) return;
  setButtonLoading($("validate"), true, "Checking evidence");
  setStatus("Reading show commands…");
  showTyping();

  try {
    await delay(500);
    currentValidation = await get(`/api/cases/${selected.case_id}/validate`);
    hideTyping();

    addBubble("sage", renderValidationFindings(currentValidation), true);
    $("diagnose").disabled = false;
    setStep("check");
    setStatus("Evidence checked — ready for a suggestion");
    toast("Evidence check done");
  } catch (error) {
    hideTyping();
    addBubble("sage", `<p>Hmm, that didn't work: ${error.message}</p>`, true);
    setStatus("Something went wrong");
  } finally {
    setButtonLoading($("validate"), false);
  }
});

$("diagnose").addEventListener("click", async () => {
  if (!selected) return;
  setButtonLoading($("diagnose"), true, "Thinking it through");
  setStatus("Sage is thinking…");
  addUserAction("What do you think is going on?");
  showTyping();

  try {
    await delay(650);
    currentDiagnosis = await get("/api/diagnose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: selected.case_id }),
    });
    hideTyping();

    addBubble("sage", renderDiagnosisMessage(currentDiagnosis), true);
    $("review").hidden = false;
    setStep("diagnose");
    setStatus("Waiting for your review");
    toast("Suggestion ready — your turn to review");
    $("review").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    hideTyping();
    addBubble("sage", `<p>I hit a snag: ${error.message}</p>`, true);
    setStatus("Diagnosis failed");
  } finally {
    setButtonLoading($("diagnose"), false);
  }
});

document.querySelectorAll("[data-status]").forEach((button) => {
  button.addEventListener("click", async () => {
    const status = button.dataset.status;
    const reviewerName = $("reviewerName").value.trim();
    const correction = $("correction").value.trim();

    if (!reviewerName) {
      $("reviewMessage").textContent = "Pop your name in first — we need a real human on the record.";
      $("reviewMessage").className = "feedback error";
      $("reviewerName").focus();
      return;
    }

    if (status !== "Accepted" && !correction) {
      $("reviewMessage").textContent = "Tell us what you'd change — even a short note helps the next person.";
      $("reviewMessage").className = "feedback error";
      $("correction").focus();
      return;
    }

    try {
      await get(`/api/cases/${selected.case_id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status,
          reviewer_name: reviewerName,
          corrected_diagnosis: status === "Edited" ? correction : null,
          reason: correction || "Reviewer accepted the evidence-backed diagnosis.",
        }),
      });

      addUserAction(
        status === "Accepted"
          ? `${reviewerName}: Looks good, I accept this.`
          : `${reviewerName}: ${status === "Edited" ? "I'd tweak it — " : "Rejecting because — "}${correction}`,
      );
      addBubble(
        "sage",
        `<p>Thanks, ${reviewerName}. Recorded as <strong>${status}</strong>. Run the verification command in Packet Tracer when you get a chance — that's what makes it real.</p>`,
        true,
      );

      $("reviewMessage").textContent = `${status} saved. Nice work — that's responsible troubleshooting.`;
      $("reviewMessage").className = "feedback success";
      setStep("review");
      setStatus("Review complete");
      toast(`${status} — saved to the audit trail`);

      // Dynamically update dashboard and spreadsheet in real time!
      await refreshDashboard();
    } catch (error) {
      $("reviewMessage").textContent = error.message;
      $("reviewMessage").className = "feedback error";
    }
  });
});

load().catch((error) => {
  $("title").textContent = "Couldn't load lab tickets";
  $("symptom").textContent = error.message;
  setStatus("Offline");
});
