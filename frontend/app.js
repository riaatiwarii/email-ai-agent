const apiBaseUrlInput = document.getElementById("apiBaseUrl");
const saveApiBaseUrlButton = document.getElementById("saveApiBaseUrl");
const ingestForm = document.getElementById("ingestForm");
const accountForm = document.getElementById("accountForm");
const accountStatus = document.getElementById("accountStatus");
const activityConsole = document.getElementById("activityConsole");
const metricsEl = document.getElementById("metrics");
const emailListEl = document.getElementById("emailList");
const emailDetailEl = document.getElementById("emailDetail");
const pendingTasksEl = document.getElementById("pendingTasks");
const notesListEl = document.getElementById("notesList");

let selectedEmailId = null;
let cachedEmails = [];

apiBaseUrlInput.value = localStorage.getItem("email-ai-agent-api") || "http://localhost:8000";

function getApiBaseUrl() {
  return apiBaseUrlInput.value.replace(/\/$/, "");
}

async function apiFetch(path, options = {}) {
  const response = await fetch(`${getApiBaseUrl()}${path}`, options);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail || JSON.stringify(data));
  }

  return data;
}

function writeConsole(value) {
  activityConsole.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function writeAccountConsole(value) {
  accountStatus.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function statusClass(status) {
  if (status === "PENDING_APPROVAL") return "status-pill pending";
  if (status.includes("FAILED") || status === "REJECTED" || status === "NO_ACTION") return "status-pill warn";
  return "status-pill";
}

function statusPill(status) {
  return `<span class="${statusClass(status)}">${status}</span>`;
}

function summarize(text, length = 140) {
  if (!text) return "";
  return text.length > length ? `${text.slice(0, length)}...` : text;
}

function metricCard(label, value) {
  return `
    <article class="metric-card">
      <span>${label}</span>
      <strong>${value}</strong>
    </article>
  `;
}

function renderMetrics(overview) {
  metricsEl.innerHTML = [
    metricCard("Emails", overview.total_emails),
    metricCard("Tasks", overview.total_tasks),
    metricCard("Pending Approval", overview.pending_approval),
    metricCard("Approved", overview.approved),
    metricCard("Executed", overview.executed),
    metricCard("Failures", overview.failed),
    metricCard("Notes", overview.notes),
  ].join("");
}

function renderEmailList(emails) {
  cachedEmails = emails;
  if (!emails.length) {
    emailListEl.innerHTML = `<div class="empty">No emails yet. Sync a real inbox or add one manually.</div>`;
    return;
  }

  emailListEl.innerHTML = emails.map((email) => `
    <article class="email-card ${email.id === selectedEmailId ? "active" : ""}" data-email-id="${email.id}">
      <div class="card-topline">
        ${statusPill(email.status)}
        <span>${email.source || "manual"}</span>
      </div>
      <p class="card-title">${email.subject || "(no subject)"}</p>
      <p class="card-copy">${summarize(email.raw_body || email.cleaned_body || "No body")}</p>
      <div class="card-topline">
        <small>${email.from_address || "Unknown sender"}</small>
        <strong>${email.task_count} task(s)</strong>
      </div>
    </article>
  `).join("");
}

function renderTaskCard(task, interactive) {
  const calendarLink = task.action_type === "SCHEDULE_MEETING" && task.payload.google_calendar_url
    ? `<a class="link-chip" href="${task.payload.google_calendar_url}" target="_blank" rel="noreferrer">Open Calendar Draft</a>`
    : "";

  const buttons = interactive
    ? `
      <div class="card-actions">
        <button data-action="approve" data-task-id="${task.id}">Approve</button>
        <button class="warm" data-action="reject" data-task-id="${task.id}">Reject</button>
      </div>
    `
    : "";

  return `
    <article class="task-card">
      <div class="card-topline">
        <strong>${task.payload.title || task.action_type}</strong>
        ${statusPill(task.status)}
      </div>
      <p class="card-copy">${task.payload.rationale || ""}</p>
      <div class="code-block">${JSON.stringify(task.payload, null, 2)}</div>
      ${calendarLink}
      ${buttons}
    </article>
  `;
}

function renderPendingTasks(tasks) {
  if (!tasks.length) {
    pendingTasksEl.className = "task-stack empty";
    pendingTasksEl.innerHTML = "No tasks waiting for approval.";
    return;
  }

  pendingTasksEl.className = "task-stack";
  pendingTasksEl.innerHTML = tasks.map((task) => renderTaskCard(task, true)).join("");
}

function renderNotes(notes) {
  if (!notes.length) {
    notesListEl.className = "notes-stack empty";
    notesListEl.innerHTML = "No notes saved yet.";
    return;
  }

  notesListEl.className = "notes-stack";
  notesListEl.innerHTML = notes.map((note) => `
    <article class="note-card">
      <div class="card-topline">
        <strong>${note.title || "Untitled note"}</strong>
        <span>#${note.id}</span>
      </div>
      <p class="card-copy">${summarize(note.content || "", 220)}</p>
    </article>
  `).join("");
}

function renderEmailDetail(detail) {
  const email = detail.email;
  const taskSection = detail.tasks.length
    ? detail.tasks.map((task) => renderTaskCard(task, false)).join("")
    : `<div class="empty">No tasks for this email.</div>`;
  const notesSection = detail.notes.length
    ? detail.notes.map((note) => `
      <article class="note-card">
        <div class="card-topline">
          <strong>${note.title || "Untitled note"}</strong>
          <span>#${note.id}</span>
        </div>
        <p class="card-copy">${summarize(note.content || "", 220)}</p>
      </article>
    `).join("")
    : `<div class="empty">No notes tied to this email yet.</div>`;
  const logsSection = detail.action_logs.length
    ? detail.action_logs.map((log) => `
      <article class="log-card">
        <div class="card-topline">
          <strong>${log.status}</strong>
          <span>${new Date(log.created_at).toLocaleString()}</span>
        </div>
        <p class="card-copy">${log.response || ""}</p>
      </article>
    `).join("")
    : `<div class="empty">No action logs yet.</div>`;

  emailDetailEl.innerHTML = `
    <div class="detail-layout">
      <div class="detail-meta">
        <div class="card-topline">
          <div>
            <p class="eyebrow">${email.source || "manual"}</p>
            <h3>${email.subject || "(no subject)"}</h3>
          </div>
          ${statusPill(email.status)}
        </div>
        <p class="card-copy">${email.raw_body || email.cleaned_body || ""}</p>
      </div>
      <div class="detail-grid">
        <section class="detail-block">
          <h4>Message</h4>
          <p><strong>From:</strong> ${email.from_address || "Unknown"}</p>
          <p><strong>To:</strong> ${email.to_address || "Unknown"}</p>
          <p><strong>Message ID:</strong> ${email.message_id}</p>
        </section>
        <section class="detail-block">
          <h4>Tasks</h4>
          <div class="task-stack">${taskSection}</div>
        </section>
      </div>
      <div class="detail-grid">
        <section class="detail-block">
          <h4>Notes</h4>
          <div class="notes-stack">${notesSection}</div>
        </section>
        <section class="detail-block">
          <h4>Action Logs</h4>
          <div class="notes-stack">${logsSection}</div>
        </section>
      </div>
    </div>
  `;
}

async function refreshDashboard() {
  try {
    const [overview, emails, tasks, notes] = await Promise.all([
      apiFetch("/overview"),
      apiFetch("/emails"),
      apiFetch("/tasks?status=PENDING_APPROVAL"),
      apiFetch("/notes"),
    ]);

    renderMetrics(overview);
    renderEmailList(emails);
    renderPendingTasks(tasks);
    renderNotes(notes);

    if (!selectedEmailId && emails.length) {
      selectedEmailId = emails[0].id;
    }

    if (selectedEmailId) {
      await loadEmailDetail(selectedEmailId, false);
    }
  } catch (error) {
    writeConsole(`Refresh failed: ${error.message}`);
  }
}

async function loadEmailDetail(emailId, announce = true) {
  try {
    const detail = await apiFetch(`/emails/${emailId}`);
    selectedEmailId = emailId;
    renderEmailList(cachedEmails);
    renderEmailDetail(detail);
    if (announce) {
      writeConsole(detail);
    }
  } catch (error) {
    writeConsole(`Failed to load email detail: ${error.message}`);
  }
}

async function submitManualEmail(event) {
  event.preventDefault();
  const formData = new FormData(ingestForm);
  const payload = Object.fromEntries(formData.entries());
  if (!payload.message_id) {
    payload.message_id = `manual-${Date.now()}`;
  }

  try {
    const data = await apiFetch("/ingest-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    writeConsole(data);
    await refreshDashboard();
  } catch (error) {
    writeConsole(`Manual ingest failed: ${error.message}`);
  }
}

function accountPayload() {
  const formData = new FormData(accountForm);
  const payload = Object.fromEntries(formData.entries());
  payload.imap_port = 993;
  payload.smtp_port = 587;
  payload.use_tls = true;
  payload.limit = 10;
  payload.unread_only = true;
  return payload;
}

async function testAccount() {
  try {
    const data = await apiFetch("/email-account/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(accountPayload()),
    });
    writeAccountConsole(data);
  } catch (error) {
    writeAccountConsole(`Connection test failed: ${error.message}`);
  }
}

async function syncInbox() {
  try {
    const data = await apiFetch("/sync-inbox", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(accountPayload()),
    });
    writeAccountConsole(data);
    writeConsole(data);
    await refreshDashboard();
  } catch (error) {
    writeAccountConsole(`Inbox sync failed: ${error.message}`);
  }
}

async function handleTaskAction(event) {
  const button = event.target.closest("button[data-task-id]");
  if (!button) {
    return;
  }

  const taskId = button.dataset.taskId;
  const action = button.dataset.action;

  try {
    const data = await apiFetch(`/tasks/${taskId}/${action}`, { method: "POST" });
    writeConsole(data);
    await refreshDashboard();
  } catch (error) {
    writeConsole(`Task action failed: ${error.message}`);
  }
}

function loadSeedExample() {
  ingestForm.elements.message_id.value = `demo-${Date.now()}`;
  ingestForm.elements.from_address.value = "recruiter@example.com";
  ingestForm.elements.to_address.value = "you@example.com";
  ingestForm.elements.subject.value = "Interview follow-up and scheduling";
  ingestForm.elements.raw_body.value =
    "Please send your resume, remind me tomorrow, and let's schedule a meeting next week. Also take note of the portfolio feedback.";
}

saveApiBaseUrlButton.addEventListener("click", () => {
  localStorage.setItem("email-ai-agent-api", getApiBaseUrl());
  writeConsole({ api_base_url: getApiBaseUrl(), saved: true });
});

document.getElementById("refreshAll").addEventListener("click", refreshDashboard);
document.getElementById("seedExample").addEventListener("click", loadSeedExample);
document.getElementById("testAccount").addEventListener("click", testAccount);
document.getElementById("syncInbox").addEventListener("click", syncInbox);
ingestForm.addEventListener("submit", submitManualEmail);
emailListEl.addEventListener("click", (event) => {
  const card = event.target.closest("[data-email-id]");
  if (!card) {
    return;
  }
  loadEmailDetail(Number(card.dataset.emailId));
});
pendingTasksEl.addEventListener("click", handleTaskAction);

loadSeedExample();
refreshDashboard();
