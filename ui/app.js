/**
 * OpenClaw Chat UI – App Logic
 * Talks to the Node.js Gateway at the same origin (or localhost:3000)
 */

const GATEWAY = ""; // empty = same origin; change to "http://localhost:3000" for dev

// ─── DOM Refs ──────────────────────────────────────────────────────────────
const messagesEl = document.getElementById("messages");
const userInput = document.getElementById("user-input");
const btnSend = document.getElementById("btn-send");
const btnClear = document.getElementById("btn-clear");
const btnMenu = document.getElementById("btn-menu");
const btnIngest = document.getElementById("btn-ingest");
const sidebar = document.getElementById("sidebar");
const statusDot = document.getElementById("status-dot");
const statusLabel = document.getElementById("status-label");
const drawer = document.getElementById("thinking-drawer");
const thinkingPre = document.getElementById("thinking-content");
const btnCloseDrawer = document.getElementById("btn-close-drawer");
const overlay = document.getElementById("overlay");

// ─── Status helpers ────────────────────────────────────────────────────────
function setStatus(state, label) {
    statusDot.className = `status-dot ${state}`;
    statusLabel.textContent = label;
}

async function checkHealth() {
    try {
        const r = await fetch(`${GATEWAY}/health`);
        if (r.ok) setStatus("online", "Online");
        else setStatus("offline", "Error");
    } catch {
        setStatus("offline", "Unreachable");
    }
}
checkHealth();
setInterval(checkHealth, 15_000);

// ─── RAID Alerts Polling ───────────────────────────────────────────────────
function _buildRaidAlertItem(a) {
    const li = document.createElement("li");

    const proj = document.createElement("strong");
    proj.textContent = "[" + a.ProjectNumber + "] " + a.raidID + ": ";
    li.appendChild(proj);

    const descRaw   = typeof a.Description === "string" ? a.Description.replace(/<\/?[^>]+(>|$)/g, "") : "";
    const shortDesc = descRaw.length > 60 ? descRaw.substring(0, 57) + "…" : descRaw || "No Description";
    li.appendChild(document.createTextNode(shortDesc + " "));

    const due = document.createElement("strong");
    due.textContent = "(Due: " + a.DueDate + ")";
    li.appendChild(due);

    if (a.owner && a.owner.toLowerCase() !== "unassigned") {
        li.appendChild(document.createTextNode(" (Owner: " + a.owner + ")"));
    }
    return li;
}

async function fetchRaidAlerts() {
    try {
        const res = await fetch(`http://localhost:8000/raid/alerts`);
        const data = await res.json();

        const chatContainer = document.getElementById("raid-alerts-container");
        const chatList      = document.getElementById("raid-alerts-list");
        const dbContainer   = document.getElementById("db-raid-alerts-container");
        const dbList        = document.getElementById("db-raid-alerts-list");

        if (data.alerts && data.alerts.length > 0) {
            [chatList, dbList].forEach(list => {
                if (!list) return;
                list.replaceChildren(...data.alerts.map(_buildRaidAlertItem));
            });
            if (chatContainer) chatContainer.style.display = "block";
            if (dbContainer)   dbContainer.style.display   = "block";
        } else {
            if (chatContainer) chatContainer.style.display = "none";
            if (dbContainer)   dbContainer.style.display   = "none";
        }
    } catch (e) {
        // fail silently
    }
}
// Initial fetch and poll every 30 seconds
fetchRaidAlerts();
setInterval(fetchRaidAlerts, 30_000);

// ─── Doc Browser ───────────────────────────────────────────────────────────
const docsBtnToggle = document.getElementById("btn-docs-toggle");
const docsListEl    = document.getElementById("sidebar-docs-list");
let _docsLoaded = false;

docsBtnToggle?.addEventListener("click", () => {
    const open = docsBtnToggle.getAttribute("aria-expanded") === "true";
    docsBtnToggle.setAttribute("aria-expanded", String(!open));
    docsListEl.hidden = open;
    if (!open && !_docsLoaded) loadDocBrowser();
});

async function loadDocBrowser() {
    _docsLoaded = true;
    docsListEl.textContent = "Loading…";
    try {
        const r    = await fetch(`${GATEWAY}/docs`);
        const data = await r.json();
        renderDocBrowser(data.projects || []);
    } catch {
        docsListEl.textContent = "Could not load documents.";
    }
}

function renderDocBrowser(projects) {
    docsListEl.replaceChildren();
    if (!projects.length) {
        const msg = document.createElement("p");
        msg.className = "sidebar-docs-empty";
        msg.textContent = "No documents uploaded yet.";
        docsListEl.appendChild(msg);
        return;
    }
    const EXT_ICON = { ".pdf": "📄", ".docx": "📝", ".doc": "📝", ".xlsx": "📊", ".xls": "📊" };
    for (const proj of projects) {
        const grp = document.createElement("div");
        grp.className = "sidebar-docs-group";

        const hdr = document.createElement("div");
        hdr.className = "sidebar-docs-group-name";
        hdr.textContent = proj.project;
        grp.appendChild(hdr);

        for (const file of proj.files) {
            const btn = document.createElement("button");
            btn.className = "sidebar-docs-file";
            btn.title = file.name + " (" + file.size_kb + " KB)";
            const icon = EXT_ICON[file.ext] || "📎";
            btn.textContent = icon + " " + file.name;
            btn.addEventListener("click", () => {
                switchTab("chat");
                userInput.value = "Show me the " + file.name + " for " + proj.project;
                sendMessage();
            });
            grp.appendChild(btn);
        }
        docsListEl.appendChild(grp);
    }
}

// ─── Agent badge config ────────────────────────────────────────────────────
const AGENT_META = {
    "plan-forecast_agent": { label: "📊 Plan-Forecast Agent", css: "badge-forecast" },
    "contract_agent": { label: "📜 Contract Agent", css: "badge-contract" },
    "general_agent": { label: "💬 General Agent", css: "badge-general" },
    "pricing_agent": { label: "💰 Pricing Agent", css: "badge-both" },
    "risk_agent": { label: "⚠️ Risk Agent", css: "badge-contract" },
    "raid_update_agent": { label: "⚡ RAID Update", css: "badge-both" },
    "both": { label: "⚖️  Synthesizer", css: "badge-both" },
};

function getAgentMeta(agent) {
    return AGENT_META[agent] || { label: agent, css: "badge-general" };
}

// ─── Message rendering ─────────────────────────────────────────────────────
function appendMessage(role, text, { agent = null, debugLog = null } = {}) {
    const wrapper = document.createElement("div");
    wrapper.className = `message ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = role === "user" ? "👤" : "🤖";

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    if (agent && role === "assistant") {
        const meta = getAgentMeta(agent);
        const badge = document.createElement("span");
        badge.className = `agent-badge ${meta.css}`;
        badge.textContent = meta.label;
        bubble.appendChild(badge);

        // Highlight sidebar chip
        document.querySelectorAll(".agent-chip").forEach(c => c.classList.remove("active"));
        const chip = document.querySelector(`[data-agent="${agent}"]`);
        if (chip) chip.classList.add("active");
    }

    // Render markdown-ish text (bold only, for brevity)
    const content = document.createElement("div");
    content.innerHTML = formatText(text);
    bubble.appendChild(content);

    if (debugLog) {
        const link = document.createElement("a");
        link.className = "thinking-link";
        link.textContent = "🧠 View thinking process →";
        link.onclick = () => showDrawer(debugLog);
        bubble.appendChild(link);
    }

    wrapper.appendChild(avatar);
    wrapper.appendChild(bubble);
    messagesEl.appendChild(wrapper);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return wrapper;
}

function formatText(text) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, `<code style="background:#21262d;padding:1px 5px;border-radius:4px;font-family:var(--mono)">$1</code>`)
        .replace(/\n/g, "<br>");
}

function appendLoading() {
    const wrapper = document.createElement("div");
    wrapper.className = "message assistant";
    wrapper.id = "loading-msg";
    wrapper.innerHTML = `
    <div class="avatar">🤖</div>
    <div class="bubble loading-bubble">
      <div class="dots">
        <span></span><span></span><span></span>
      </div>
    </div>`;
    messagesEl.appendChild(wrapper);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

function removeLoading() {
    document.getElementById("loading-msg")?.remove();
}

// ─── Send message ──────────────────────────────────────────────────────────
async function sendMessage(query) {
    if (!query.trim()) return;

    appendMessage("user", query);
    userInput.value = "";
    userInput.style.height = "auto";
    btnSend.disabled = true;
    setStatus("thinking", "Thinking…");
    appendLoading();

    try {
        const res = await fetch(`${GATEWAY}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query }),
        });

        removeLoading();

        if (!res.ok) {
            const err = await res.json();
            appendMessage("assistant", `❌ Error: ${err.error || res.statusText}`);
            setStatus("offline", "Error");
            return;
        }

        const data = await res.json();
        appendMessage("assistant", data.response, {
            agent: data.agent,
            debugLog: data.debug_log,
        });
        setStatus("online", "Online");

    } catch (err) {
        removeLoading();
        appendMessage("assistant",
            "❌ Cannot reach the OpenClaw Gateway.\n\nMake sure the Node.js server is running:\n`cd runtime && node gateway/server.js`"
        );
        setStatus("offline", "Unreachable");
    } finally {
        btnSend.disabled = false;
        userInput.focus();
    }
}

// ─── Thinking drawer ───────────────────────────────────────────────────────
function showDrawer(log) {
    thinkingPre.textContent = log || "No log available.";
    drawer.classList.remove("hidden");
    overlay.classList.add("visible");
}
function hideDrawer() {
    drawer.classList.add("hidden");
    overlay.classList.remove("visible");
}
btnCloseDrawer.addEventListener("click", hideDrawer);
overlay.addEventListener("click", hideDrawer);

// ─── Event listeners ───────────────────────────────────────────────────────
btnSend.addEventListener("click", () => sendMessage(userInput.value));

userInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage(userInput.value);
    }
});

// Auto-grow textarea
userInput.addEventListener("input", () => {
    userInput.style.height = "auto";
    userInput.style.height = Math.min(userInput.scrollHeight, 200) + "px";
});

btnClear.addEventListener("click", () => {
    messagesEl.innerHTML = "";
    document.querySelectorAll(".agent-chip").forEach(c => c.classList.remove("active"));
});

btnMenu.addEventListener("click", () => {
    sidebar.classList.toggle("open");
    overlay.classList.toggle("visible");
});

// Example chips
document.addEventListener("click", e => {
    if (e.target.matches(".chip[data-q]")) {
        sendMessage(e.target.dataset.q);
    }
});

// Re-ingest
btnIngest.addEventListener("click", async () => {
    btnIngest.textContent = "⏳ Ingesting…";
    btnIngest.disabled = true;
    try {
        const r = await fetch(`${GATEWAY}/ingest`, { method: "POST" });
        const d = await r.json();
        const count = Object.keys(d.indexed || {}).length;
        appendMessage("assistant", `✅ Re-ingestion complete! Indexed **${count}** document collection(s).`);
    } catch {
        appendMessage("assistant", "❌ Ingestion failed. Check server logs.");
    } finally {
        btnIngest.textContent = "🗄️ Re-Ingest Docs";
        btnIngest.disabled = false;
    }
});

// ─── Tab Navigation (Chat / Create / Dashboard) ──────────────────────────────
const navChat      = document.getElementById("nav-chat");
const navCreate    = document.getElementById("nav-create");
const navDashboard = document.getElementById("nav-dashboard");
const mainEl       = document.getElementById("main");
const createPanel  = document.getElementById("create-panel");
const dashPanel    = document.getElementById("dashboard-panel");

function switchTab(tab) {
    // hide all panels
    mainEl.style.display = "none";
    createPanel.classList.add("hidden-panel");
    dashPanel.classList.add("hidden-panel");
    [navChat, navCreate, navDashboard].forEach(b => b?.classList.remove("nav-active"));

    if (tab === "chat") {
        mainEl.style.display = "flex";
        navChat.classList.add("nav-active");
    } else if (tab === "create") {
        createPanel.classList.remove("hidden-panel");
        createPanel.style.display = "flex";
        navCreate.classList.add("nav-active");
    } else if (tab === "dashboard") {
        dashPanel.classList.remove("hidden-panel");
        dashPanel.style.display = "flex";
        dashPanel.style.flexDirection = "column";
        navDashboard.classList.add("nav-active");
        loadDashboard();
    }
}

navChat.addEventListener("click",      () => switchTab("chat"));
navCreate.addEventListener("click",    () => switchTab("create"));
navDashboard.addEventListener("click", () => switchTab("dashboard"));

// Mobile sidebar toggle for create/dashboard panels
document.getElementById("btn-menu-create")?.addEventListener("click", () => {
    sidebar.classList.toggle("open");
    overlay.classList.toggle("visible");
});
document.getElementById("btn-menu-dashboard")?.addEventListener("click", () => {
    sidebar.classList.toggle("open");
    overlay.classList.toggle("visible");
});

// ─── Project Creation Flow ──────────────────────────────────────────────────
const projectForm = document.getElementById("project-form");
const createStatus = document.getElementById("create-status");
const confirmSection = document.getElementById("confirmation-section");
const tableWrapper = document.getElementById("extracted-table-wrapper");
const confirmStatus = document.getElementById("confirm-status");

let pendingProjectData = null; // stores { project_name, project_code, opportunity_id, extracted_data }

// ─── File Upload Validation ─────────────────────────────────────────────────
const VALID_CONTRACT_EXT = [".docx", ".doc", ".pdf"];
const VALID_EXCEL_EXT = [".xlsx", ".xls"];

function getFileExt(filename) {
    return (filename || "").substring(filename.lastIndexOf(".")).toLowerCase();
}

function validateFileUpload(inputId, statusId, validExtensions, structureHint) {
    const input = document.getElementById(inputId);
    const status = document.getElementById(statusId);
    if (!input || !status) return;

    input.addEventListener("change", () => {
        const file = input.files[0];
        if (!file) { status.textContent = ""; status.className = "file-status"; return; }

        const ext = getFileExt(file.name);
        if (!validExtensions.includes(ext)) {
            status.textContent = `❌ Invalid file type "${ext}". Expected: ${validExtensions.join(", ")}`;
            status.className = "file-status invalid";
            return;
        }

        // Additional structure hints based on filename
        if (structureHint === "contract") {
            status.textContent = `✅ ${file.name} — will be ingested into Contract collection`;
            status.className = "file-status valid";
        } else if (structureHint === "estimation") {
            const nameLower = file.name.toLowerCase();
            if (nameLower.includes("estimat") || nameLower.includes("milestone") || nameLower.includes("resource")) {
                status.textContent = `✅ ${file.name} — will be ingested into Estimation-Milestone collection`;
                status.className = "file-status valid";
            } else {
                status.textContent = `⚠️ ${file.name} — filename doesn't contain "estimation" or "milestone". Please verify this is the correct file.`;
                status.className = "file-status invalid";
            }
        } else if (structureHint === "project") {
            const nameLower = file.name.toLowerCase();
            if (nameLower.includes("project") || nameLower.includes("erp") || nameLower.includes("data")) {
                status.textContent = `✅ ${file.name} — will be ingested into Project collection`;
                status.className = "file-status valid";
            } else {
                status.textContent = `⚠️ ${file.name} — filename doesn't contain "project" or "ERP". Please verify this is the correct file.`;
                status.className = "file-status invalid";
            }
        }
    });
}

validateFileUpload("inp-contract-file", "contract-file-status", VALID_CONTRACT_EXT, "contract");
validateFileUpload("inp-estimation-file", "estimation-file-status", VALID_EXCEL_EXT, "estimation");
validateFileUpload("inp-erp-file", "erp-file-status", VALID_EXCEL_EXT, "project");


projectForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const projectName = document.getElementById("inp-project-name").value.trim();
    const projectCode = document.getElementById("inp-project-code").value.trim();
    const opportunityId = document.getElementById("inp-opportunity-id").value.trim();
    const contractFile = document.getElementById("inp-contract-file").files[0];
    const estimationFile = document.getElementById("inp-estimation-file").files[0];
    const erpFile = document.getElementById("inp-erp-file")?.files[0];

    if (!projectName || !projectCode || !contractFile || !estimationFile) {
        createStatus.innerHTML = "❌ Please fill in Project Name, Project Code, and upload the required files.";
        return;
    }

    const formData = new FormData();
    formData.append("project_name", projectName);
    formData.append("project_code", projectCode);
    formData.append("opportunity_id", opportunityId);
    formData.append("contract_file", contractFile);
    formData.append("estimation_file", estimationFile);
    if (erpFile) {
        formData.append("erp_file", erpFile);
    }

    const btn = document.getElementById("btn-create-project");
    btn.disabled = true;
    btn.textContent = "⏳ Extracting project data…";
    createStatus.innerHTML = "📥 Uploading and ingesting documents… this may take a minute.";

    try {
        const res = await fetch(`${GATEWAY}/project/create`, {
            method: "POST",
            body: formData,
        });

        if (!res.ok) {
            const err = await res.json();
            createStatus.innerHTML = `❌ Error: ${err.detail || res.statusText}`;
            return;
        }

        const data = await res.json();
        pendingProjectData = {
            project_name: data.project_name,
            project_code: data.project_code,
            opportunity_id: data.opportunity_id,
            extracted_data: data.extracted_data,
        };

        createStatus.innerHTML = "✅ Data extracted! Please review below.";
        renderConfirmationTable(data.extracted_data);
        confirmSection.classList.remove("hidden-panel");
        confirmSection.style.display = "block";

    } catch (err) {
        createStatus.innerHTML = `❌ Connection error: ${err.message}`;
    } finally {
        btn.disabled = false;
        btn.textContent = "🚀 Create Project";
    }
});


// JSON fields require expandable textarea editors
const JSON_FIELDS = new Set([
    "sow_json", "resources_json", "invoice_json",
    "revenue_json", "total_hours_json", "work_packages"
]);

function renderConfirmationTable(data) {
    const friendlyLabels = {
        ProjectNumber: "Project Number",
        OpportunityID: "Opportunity ID",
        customer: "Customer",
        end_customer: "End Customer",
        PMName: "Project Manager",
        DMName: "Delivery Manager",
        country: "Country",
        startdateContract: "Contract Start Date",
        endDateContract: "Contract End Date",
        startdateBaseline: "Baseline Start Date",
        endDateBaseline: "Baseline End Date",
        exchangerate: "Exchange Rate",
        MBRReporting_currency: "Reporting Currency",
        Proj_Stage: "Project Stage",
        Contr_Type: "Contract Type",
        Rev_Type: "Revenue Type",
        Baseline_Rev: "Baseline Revenue",
        Baseline_Cost: "Baseline Cost",
        Prod_Grp: "Product Group",
        Portfolio: "Portfolio",
        Region: "Region",
        Project_Owner: "Project Owner",
        invoice_json: "Invoice Data",
        revenue_json: "Revenue Data",
    };

    let html = '<table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>';
    for (const [key, value] of Object.entries(data)) {
        const label = friendlyLabels[key] || key;
        const val = value ?? "";

        if (JSON_FIELDS.has(key) && val) {
            // Format JSON nicely for display
            let formatted = val;
            try {
                const parsed = typeof val === "string" ? JSON.parse(val) : val;
                formatted = JSON.stringify(parsed, null, 2);
            } catch { formatted = String(val); }

            const uid = `json-toggle-${key}`;
            html += `<tr>
                <th>
                    ${label}
                    <button type="button" class="btn-json-toggle" onclick="
                        const el = document.getElementById('${uid}');
                        const btn = this;
                        if (el.style.display === 'none') {
                            el.style.display = 'block';
                            btn.textContent = '▼ Collapse';
                        } else {
                            el.style.display = 'none';
                            btn.textContent = '▶ Expand';
                        }
                    ">▶ Expand</button>
                </th>
                <td>
                    <div class="json-preview">${String(val).substring(0, 80)}…</div>
                    <textarea id="${uid}" data-field="${key}" class="json-textarea" style="display:none">${formatted.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</textarea>
                </td>
            </tr>`;
        } else {
            html += `<tr>
                <th>${label}</th>
                <td><input type="text" data-field="${key}" value="${String(val).replace(/"/g, '&quot;')}" /></td>
            </tr>`;
        }
    }
    html += '</tbody></table>';
    tableWrapper.innerHTML = html;
}

// Confirm & Save
document.getElementById("btn-confirm-save")?.addEventListener("click", async () => {
    if (!pendingProjectData) {
        confirmStatus.innerHTML = "❌ No project data to confirm.";
        return;
    }

    // Read edited values from the table (inputs for flat fields, textareas for JSON)
    const inputs = tableWrapper.querySelectorAll("input[data-field], textarea[data-field]");
    const editedData = {};
    inputs.forEach(inp => {
        let val = inp.value.trim();
        if (val && inp.tagName === "TEXTAREA" && JSON_FIELDS.has(inp.dataset.field)) {
            try {
                // Parse it back to object/array so it isn't sent as a raw string
                // Especially for work_packages which the DB agent needs as a list
                val = JSON.parse(val);
            } catch (e) {
                console.warn("Failed to parse JSON for", inp.dataset.field, e);
            }
        }
        editedData[inp.dataset.field] = val || null;
    });

    // Try to parse numeric fields
    for (const numField of ["Baseline_Rev", "Baseline_Cost"]) {
        if (editedData[numField] && !isNaN(editedData[numField])) {
            editedData[numField] = Number(editedData[numField]);
        }
    }

    const btn = document.getElementById("btn-confirm-save");
    btn.disabled = true;
    btn.textContent = "⏳ Saving…";
    confirmStatus.innerHTML = "💾 Persisting to database…";

    try {
        const res = await fetch(`${GATEWAY}/project/confirm`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                project_name: pendingProjectData.project_name,
                project_code: pendingProjectData.project_code,
                opportunity_id: pendingProjectData.opportunity_id,
                extracted_data: editedData,
            }),
        });

        const data = await res.json();
        if (data.status === "created") {
            confirmStatus.innerHTML = `✅ ${data.response.replace(/\n/g, "<br>")}`;
            projectForm.reset();
            pendingProjectData = null;
        } else {
            confirmStatus.innerHTML = `⚠️ ${data.response.replace(/\n/g, "<br>")}`;
        }
    } catch (err) {
        confirmStatus.innerHTML = `❌ Error: ${err.message}`;
    } finally {
        btn.disabled = false;
        btn.textContent = "✅ Confirm & Save";
    }
});

// Cancel
document.getElementById("btn-cancel-create")?.addEventListener("click", () => {
    confirmSection.classList.add("hidden-panel");
    pendingProjectData = null;
    confirmStatus.innerHTML = "";
    createStatus.innerHTML = "";
});

// ═══════════════════════════════════════════════════════════════════════════
// ─── Dashboard Logic ───────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

/* Safe DOM builder */
function dbEl(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) Object.entries(attrs).forEach(([k, v]) => {
        if (k === "className") node.className = v;
        else if (k === "title") node.title = v;
        else node.setAttribute(k, v);
    });
    (children || []).forEach(c => {
        if (c == null) return;
        node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
}

const DB_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function dbFmtDate(d) {
    return String(d.getDate()).padStart(2,"0") + " " + DB_MONTHS[d.getMonth()] + " " + d.getFullYear();
}

function dbFmtCurrency(val, currency) {
    if (val == null) return "—";
    const abs = Math.abs(val);
    const s = abs >= 1e6 ? (abs / 1e6).toFixed(2) + "M"
            : abs >= 1e3 ? (abs / 1e3).toFixed(1) + "K"
            : abs.toFixed(0);
    return (val < 0 ? "-" : "") + (currency || "SGD") + "\u00A0" + s;
}

function dbPill(text, cls) { return dbEl("span", { className: "db-pill " + cls }, [text]); }

function dbCategoryPill(cat) {
    const c = (cat || "").toLowerCase();
    return dbPill(cat || "—", c === "high" ? "db-pill-high" : c === "medium" ? "db-pill-medium" : "db-pill-low");
}

function dbStatusPill(status) {
    const s = (status || "").toLowerCase();
    return dbPill(status || "—", s === "open" ? "db-pill-open" : s === "wip" ? "db-pill-wip" : "db-pill-closed");
}

function dbStageBadge(stage) {
    const s = (stage || "").toUpperCase();
    const map = {
        "AT RISK":  ["db-badge-at-risk",  "\uD83D\uDD34 AT RISK"],
        "DELAYED":  ["db-badge-delayed",  "\uD83D\uDFE0 DELAYED"],
        "ON TRACK": ["db-badge-on-track", "\uD83D\uDFE2 ON TRACK"],
    };
    const [cls, label] = map[s] || ["db-badge-default", "\u26AA " + (stage || "—")];
    return dbEl("span", { className: "db-badge " + cls }, [label]);
}

function dbStageCardClass(stage) {
    const s = (stage || "").toUpperCase();
    if (s === "AT RISK")  return "s-at-risk";
    if (s === "DELAYED")  return "s-delayed";
    if (s === "ON TRACK") return "s-on-track";
    return "";
}

function dbRaidTable(raids) {
    if (!raids || !raids.length) {
        return dbEl("p", { className: "db-no-raids" }, ["\u2714 No open RAID items \u2014 project is clean."]);
    }
    const thead = dbEl("thead", {}, [dbEl("tr", {}, [
        dbEl("th", {}, ["Type"]),  dbEl("th", {}, ["Priority"]),
        dbEl("th", {}, ["Owner"]), dbEl("th", {}, ["Status"]),
        dbEl("th", {}, ["Due"]),   dbEl("th", {}, ["Description"]),
    ])]);
    const tbody = dbEl("tbody", {}, raids.map(r => {
        const desc = r.Description || "";
        const shortDesc = desc.length > 120 ? desc.substring(0, 120) + "\u2026" : desc;
        return dbEl("tr", {}, [
            dbEl("td", {}, [r.Type || "—"]),
            dbEl("td", {}, [dbCategoryPill(r.Category)]),
            dbEl("td", {}, [r.owner || "—"]),
            dbEl("td", {}, [dbStatusPill(r.Status)]),
            dbEl("td", {}, [(r.DueDate || "—").substring(0, 10)]),
            dbEl("td", { style: "max-width:300px" }, [shortDesc]),
        ]);
    }));
    return dbEl("table", { className: "db-table" }, [thead, tbody]);
}

function dbExtractRecovery(report, customer) {
    if (!report) return null;
    const lines = report.split("\n");
    let inProj = false, inPlan = false, out = [];
    for (const line of lines) {
        if (!inProj && line.includes(customer)) inProj = true;
        if (inProj && line.includes("Recovery Plan")) { inPlan = true; continue; }
        if (inPlan) {
            if (line.startsWith("### ") || line.startsWith("---")) break;
            if (line.trim()) out.push(line);
        }
    }
    return out.length ? out.join("\n") : null;
}

function dbProjectCard(p, idx, report) {
    const f = p.financials;
    const stg = (p.stage || "").toUpperCase();
    const varPos = f.rev_variance >= 0;
    const needsRP = stg === "AT RISK" || stg === "DELAYED";
    const cardCls = "db-project-card " + dbStageCardClass(p.stage);

    const days = _daysRemaining(p);
    const daysLabel = isFinite(days)
        ? (days < 0 ? Math.abs(days) + "d overdue" : days + "d left")
        : "—";
    const daysCls = days < 0 ? "color:#f87171" : days < 30 ? "color:#fbbf24" : "color:#4ade80";

    const nameEl = dbEl("div", { className: "db-proj-name" }, [p.customer]);
    const metaEl = dbEl("div", { className: "db-proj-meta" }, [
        "#" + p.project_number + " \u00B7 " + (p.country || "—") +
        " \u00B7 PM: " + (p.pm || "—") +
        " \u00B7 " + (p.start_date || "?") + " \u2192 " + (p.end_date || "?"),
    ]);
    const daysEl = dbEl("span", { style: "font-size:10px;font-weight:700;padding:1px 7px;border-radius:4px;background:rgba(255,255,255,0.06);" + daysCls }, [daysLabel]);
    const titleGroup = dbEl("div", { className: "db-proj-title-grp" },
        [dbStageBadge(p.stage), dbEl("div", {}, [
            dbEl("div", { style: "display:flex;align-items:center;gap:8px;" }, [nameEl, daysEl]),
            metaEl,
        ])]);

    const varEl = varPos
        ? dbEl("div", { className: "db-fin-value db-fin-pos" }, [dbFmtCurrency(f.rev_variance, f.currency)])
        : dbEl("div", { className: "db-fin-neg-pill" }, [dbFmtCurrency(f.rev_variance, f.currency)]);

    const marginCls = f.margin_pct >= 15 ? "db-fin-pos" : f.margin_pct >= 0 ? "db-kpi-warn" : "db-fin-neg";

    const fins = dbEl("div", { className: "db-fins" }, [
        dbEl("div", { className: "db-fin-item" }, [dbEl("div", { className: "db-fin-label" }, ["Baseline Rev"]),  dbEl("div", { className: "db-fin-value" }, [dbFmtCurrency(f.baseline_rev, f.currency)])]),
        dbEl("div", { className: "db-fin-item" }, [dbEl("div", { className: "db-fin-label" }, ["Actual Cost"]),   dbEl("div", { className: "db-fin-value" }, [dbFmtCurrency(f.actual_cost, f.currency)])]),
        dbEl("div", { className: "db-fin-item" }, [dbEl("div", { className: "db-fin-label" }, ["Variance"]),      varEl]),
        dbEl("div", { className: "db-fin-item" }, [dbEl("div", { className: "db-fin-label" }, ["Margin"]),        dbEl("div", { className: "db-fin-value " + marginCls }, [f.margin_pct + "%"])]),
        dbEl("div", { className: "db-fin-item", style: "text-align:center" }, [
            dbEl("div", { className: "db-fin-label" }, ["RAID"]),
            dbEl("div", { style: "font-size:11px;margin-top:3px;display:flex;gap:4px;" }, [
                dbPill("\uD83D\uDD34\u00D7" + p.raids.high,   "db-pill-count"),
                dbPill("\uD83D\uDFE0\u00D7" + p.raids.medium, "db-pill-count"),
                dbPill("\uD83D\uDFE1\u00D7" + p.raids.low,    "db-pill-count"),
            ]),
        ]),
    ]);

    const toggleIcon = dbEl("div", { className: "db-toggle-icon" }, ["\u25BE"]);
    const hdr = dbEl("div", { className: "db-proj-hdr" }, [
        titleGroup,
        dbEl("div", { style: "display:flex;align-items:center;gap:16px;" }, [fins, toggleIcon]),
    ]);

    const raidTitle = dbEl("div", { className: "db-raid-title" }, ["Open RAID Items (" + p.raids.open + ")"]);
    const detailNodes = [raidTitle, dbRaidTable(p.open_raid_items)];

    if (needsRP) {
        const plan = dbExtractRecovery(report, p.customer);
        if (plan) {
            detailNodes.push(dbEl("div", { className: "db-recovery-box" }, [
                dbEl("div", { className: "db-recovery-title" }, ["\uD83D\uDEE0 Recovery Plan"]),
                dbEl("div", { className: "db-recovery-text" }, [plan]),
            ]));
        }
    }

    const detail = dbEl("div", { className: "db-proj-detail" }, detailNodes);
    const card = dbEl("div", { className: cardCls, id: "db-project-" + idx }, [hdr, detail]);
    hdr.addEventListener("click", () => card.classList.toggle("open"));
    return card;
}

// ── Shared helpers ────────────────────────────────────────────────────────
function _csvEsc(v) { return '"' + String(v ?? "").replace(/"/g, '""') + '"'; }

function _fmtCurrency(n, currency) {
    if (n == null) return "—";
    const abs = Math.abs(n);
    const s = abs >= 1e6 ? (abs / 1e6).toFixed(2) + "M"
            : abs >= 1e3 ? (abs / 1e3).toFixed(1) + "K"
            : abs.toFixed(0);
    return (n < 0 ? "-" : "") + (currency || "SGD") + "\u00A0" + s;
}

function _htmlEsc(s) {
    return String(s ?? "")
        .replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── CSV Export ────────────────────────────────────────────────────────────
function dbExportCSV(projects) {
    const e = _csvEsc;
    const currency = projects[0]?.financials?.currency || "SGD";
    const now      = new Date().toLocaleDateString("en-SG", { day:"2-digit", month:"short", year:"numeric" });

    // Portfolio summary block
    const totalRev  = projects.reduce((s, p) => s + (p.financials.baseline_rev || 0), 0);
    const totalCost = projects.reduce((s, p) => s + (p.financials.actual_cost  || 0), 0);
    const avgMargin = projects.length
        ? (projects.reduce((s, p) => s + p.financials.margin_pct, 0) / projects.length).toFixed(1)
        : "0.0";
    const atRisk    = projects.filter(p => ["AT RISK","DELAYED"].includes((p.stage||"").toUpperCase())).length;

    const summary = [
        [e("PORTFOLIO SUMMARY"), e("Report Date"), e(now)],
        [e("Total Projects"),          e(projects.length), ""],
        [e("At Risk / Delayed"),        e(atRisk),          ""],
        [e("Total Baseline Rev (" + currency + ")"), e(totalRev),           ""],
        [e("Total Actual Cost (" + currency + ")"),  e(totalCost),          ""],
        [e("Total Variance (" + currency + ")"),     e(totalRev - totalCost), ""],
        [e("Avg Margin %"),             e(avgMargin + "%"), ""],
        [e("Total Open RAID Items"),    e(projects.reduce((s, p) => s + p.raids.open, 0)), ""],
        [],
    ].map(r => r.join(","));

    // Project detail block
    const projHdr = [
        "Project #", "Customer", "Country", "PM", "Status",
        "Contract Start", "Contract End",
        "Baseline Rev (" + currency + ")", "Actual Cost (" + currency + ")",
        "Variance (" + currency + ")", "Margin %",
        "RAID High", "RAID Med", "RAID Low", "RAID Open",
    ].map(e).join(",");

    const projRows = projects.map(p => [
        p.project_number, p.customer, p.country || "—", p.pm || "—", p.stage || "—",
        p.start_date || "—", p.end_date || "—",
        p.financials.baseline_rev, p.financials.actual_cost,
        p.financials.rev_variance, p.financials.margin_pct + "%",
        p.raids.high, p.raids.medium, p.raids.low, p.raids.open,
    ].map(e).join(","));

    // RAID detail block
    const raidHdr = ["Project #", "Customer", "RAID ID", "Type", "Priority", "Owner", "Status", "Due Date", "Description"].map(e).join(",");
    const raidRows = [];
    projects.forEach(p => {
        (p.open_raid_items || []).forEach(r => {
            raidRows.push([
                p.project_number, p.customer,
                r.raidID || "—", r.Type || "—", r.Category || "—",
                r.owner  || "—", r.Status || "—",
                (r.DueDate || "—").substring(0, 10),
                (r.Description || "").replace(/\r?\n/g, " ").substring(0, 200),
            ].map(e).join(","));
        });
    });

    const lines = [
        ...summary,
        e("PROJECT DETAIL"),
        projHdr,
        ...projRows,
        "",
        e("OPEN RAID ITEMS"),
        raidHdr,
        ...(raidRows.length ? raidRows : [e("No open RAID items")]),
    ];

    const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
    const a    = document.createElement("a");
    a.href     = URL.createObjectURL(blob);
    a.download = "portfolio_" + new Date().toISOString().slice(0, 10) + ".csv";
    a.click();
    URL.revokeObjectURL(a.href);
}

// ── PDF Export ────────────────────────────────────────────────────────────
function dbExportPDF(projects, reportText) {
    const currency = projects[0]?.financials?.currency || "SGD";
    const dateStr  = new Date().toLocaleDateString("en-SG", { day:"2-digit", month:"short", year:"numeric" });
    const h        = _htmlEsc;
    const fc       = (n) => _fmtCurrency(n, currency);

    const totalRev  = projects.reduce((s, p) => s + (p.financials.baseline_rev || 0), 0);
    const totalCost = projects.reduce((s, p) => s + (p.financials.actual_cost  || 0), 0);
    const totalVar  = totalRev - totalCost;
    const avgMargin = projects.length
        ? (projects.reduce((s, p) => s + p.financials.margin_pct, 0) / projects.length).toFixed(1)
        : "0.0";
    const openRaids = projects.reduce((s, p) => s + p.raids.open, 0);
    const highRaids = projects.reduce((s, p) => s + p.raids.high, 0);
    const atRisk    = projects.filter(p => ["AT RISK","DELAYED"].includes((p.stage||"").toUpperCase())).length;

    const stageStyle = s => {
        const map = { "AT RISK":"#c2410c", "DELAYED":"#b91c1c", "ON TRACK":"#15803d" };
        return "background:" + (map[(s||"").toUpperCase()] || "#374151") + ";color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;";
    };

    const kpiBlock = [
        ["Total Projects",    h(projects.length), h(atRisk + " at risk / delayed"),   "#1d4ed8"],
        ["Portfolio Revenue", h(fc(totalRev)),     "Baseline across all projects",     "#15803d"],
        ["Revenue Variance",  h(fc(totalVar)),     "Avg margin: " + avgMargin + "%",   totalVar >= 0 ? "#15803d" : "#b91c1c"],
        ["Open RAID Items",   h(openRaids),        h(highRaids + " high priority"),    "#b91c1c"],
    ].map(([label, val, sub, color]) =>
        `<div style="border:1px solid #e5e7eb;border-top:4px solid ${color};border-radius:8px;padding:14px;">
           <div style="font-size:10px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.5px;">${label}</div>
           <div style="font-size:22px;font-weight:800;color:#111827;margin:4px 0;">${val}</div>
           <div style="font-size:11px;color:#9ca3af;">${sub}</div>
         </div>`
    ).join("");

    const projectCards = projects.map(p => {
        const f       = p.financials;
        const varCol  = f.rev_variance >= 0 ? "#15803d" : "#b91c1c";
        const marCol  = f.margin_pct >= 15 ? "#15803d" : f.margin_pct >= 0 ? "#b45309" : "#b91c1c";
        const leftCol = { "AT RISK":"#c2410c", "DELAYED":"#b91c1c", "ON TRACK":"#15803d" }[(p.stage||"").toUpperCase()] || "#6b7280";

        const raidRowsHtml = (p.open_raid_items || []).map(r =>
            `<tr>
               <td style="padding:4px 8px;">${h(r.Type||"—")}</td>
               <td style="padding:4px 8px;">${h(r.Category||"—")}</td>
               <td style="padding:4px 8px;">${h(r.owner||"—")}</td>
               <td style="padding:4px 8px;white-space:nowrap;">${h((r.DueDate||"—").substring(0,10))}</td>
               <td style="padding:4px 8px;">${h((r.Description||"").substring(0,120))}${(r.Description||"").length>120?"…":""}</td>
             </tr>`
        ).join("");

        const raidSection = raidRowsHtml
            ? `<div style="padding:10px 16px 0;">
                 <div style="font-size:10px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;">Open RAID Items (${p.raids.open})</div>
                 <table style="width:100%;border-collapse:collapse;font-size:11px;">
                   <thead><tr style="background:#f3f4f6;font-size:10px;color:#6b7280;">
                     <th style="padding:5px 8px;text-align:left;">Type</th>
                     <th style="padding:5px 8px;text-align:left;">Priority</th>
                     <th style="padding:5px 8px;text-align:left;">Owner</th>
                     <th style="padding:5px 8px;text-align:left;">Due</th>
                     <th style="padding:5px 8px;text-align:left;">Description</th>
                   </tr></thead>
                   <tbody>${raidRowsHtml}</tbody>
                 </table>
               </div>`
            : `<div style="padding:10px 16px;font-size:12px;color:#15803d;">&#10004; No open RAID items</div>`;

        const recovery = dbExtractRecovery(reportText, p.customer);
        const recoverySection = (["AT RISK","DELAYED"].includes((p.stage||"").toUpperCase()) && recovery)
            ? `<div style="margin:12px 16px;padding:10px 14px;background:#fef2f2;border-left:4px solid #b91c1c;border-radius:6px;">
                 <div style="font-size:10px;font-weight:800;color:#b91c1c;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;">&#128296; Recovery Plan</div>
                 <div style="font-size:11px;color:#1f2937;line-height:1.7;white-space:pre-wrap;">${h(recovery)}</div>
               </div>`
            : "";

        const stageLabel = (p.stage || "UNKNOWN").toUpperCase();
        const startD = (p.start_date || "").substring(0, 10) || "N/A";
        const endD   = (p.end_date   || "").substring(0, 10) || "N/A";
        const raidSummary = `${p.raids.open} open (${p.raids.high} High / ${p.raids.medium} Med / ${p.raids.low} Low)`;

        return `<div style="margin-bottom:16px;border:1px solid #e5e7eb;border-left:5px solid ${leftCol};border-radius:8px;overflow:hidden;page-break-inside:avoid;">
          <div style="padding:12px 16px;background:#f9fafb;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;">
              <div>
                <span style="${stageStyle(stageLabel)}">${h(stageLabel)}</span>
                <span style="font-size:14px;font-weight:700;color:#111827;margin-left:8px;">${h(p.customer)}</span>
                <div style="font-size:11px;color:#6b7280;margin-top:4px;">
                  Project #${h(p.project_number)}
                  &nbsp;&middot;&nbsp; PM: ${h(p.pm || "—")}
                  &nbsp;&middot;&nbsp; Country: ${h(p.country || "—")}
                </div>
                <div style="font-size:11px;color:#6b7280;margin-top:2px;">
                  Period: ${h(startD)} &rarr; ${h(endD)}
                  &nbsp;&middot;&nbsp; Currency: ${h(f.currency || "SGD")}
                  &nbsp;&middot;&nbsp; RAID: ${h(raidSummary)}
                </div>
              </div>
              <div style="display:flex;gap:16px;text-align:right;flex-shrink:0;">
                <div><div style="font-size:9px;color:#9ca3af;text-transform:uppercase;">Baseline Rev</div><div style="font-size:13px;font-weight:700;">${h(fc(f.baseline_rev))}</div></div>
                <div><div style="font-size:9px;color:#9ca3af;text-transform:uppercase;">Actual Cost</div><div style="font-size:13px;font-weight:700;">${h(fc(f.actual_cost))}</div></div>
                <div><div style="font-size:9px;color:#9ca3af;text-transform:uppercase;">Variance</div><div style="font-size:13px;font-weight:700;color:${varCol};">${h(fc(f.rev_variance))}</div></div>
                <div><div style="font-size:9px;color:#9ca3af;text-transform:uppercase;">Margin</div><div style="font-size:13px;font-weight:700;color:${marCol};">${h(f.margin_pct + "%")}</div></div>
              </div>
            </div>
          </div>
          ${raidSection}
          ${recoverySection}
          <div style="height:10px;"></div>
        </div>`;
    }).join("");

    const fullHtml = `<!DOCTYPE html><html lang="en"><head>
      <meta charset="UTF-8">
      <title>Portfolio Dashboard &mdash; ${dateStr}</title>
      <style>
        *{box-sizing:border-box;margin:0;padding:0;}
        body{font-family:'Segoe UI',Arial,sans-serif;color:#111827;background:#fff;padding:32px 40px;font-size:13px;}
        table td,table th{vertical-align:top;}
        @media print{body{padding:16px;}@page{margin:12mm;size:A4 landscape;}}
      </style>
    </head><body>
      <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid #1d4ed8;padding-bottom:14px;margin-bottom:22px;">
        <div>
          <div style="font-size:22px;font-weight:800;color:#1d4ed8;">Project Agent v1</div>
          <div style="font-size:13px;color:#6b7280;margin-top:2px;">Portfolio Dashboard &mdash; MBR Report</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:11px;color:#6b7280;">Report Date</div>
          <div style="font-size:14px;font-weight:700;">${dateStr}</div>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:22px;">${kpiBlock}</div>
      <div style="font-size:12px;font-weight:800;color:#1d4ed8;text-transform:uppercase;letter-spacing:.5px;border-bottom:2px solid #1d4ed8;padding-bottom:8px;margin-bottom:14px;">Projects (${projects.length})</div>
      ${projectCards}
      <div style="margin-top:20px;font-size:10px;color:#9ca3af;text-align:center;border-top:1px solid #e5e7eb;padding-top:10px;">
        Generated by Project Agent v1 &mdash; ${dateStr} &mdash; Confidential
      </div>
    </body></html>`;

    const blob = new Blob([fullHtml], { type: "text/html;charset=utf-8" });
    const url  = URL.createObjectURL(blob);
    const win  = window.open(url, "_blank");
    win.addEventListener("load", () => {
        win.print();
        URL.revokeObjectURL(url);
    });
}

let _dbRevenueChart, _dbMarginChart;

function dbRenderCharts(projects) {
    if (_dbRevenueChart) _dbRevenueChart.destroy();
    if (_dbMarginChart)  _dbMarginChart.destroy();

    const labels = projects.map(p => p.customer.split(" ").slice(0, 2).join(" "));
    const tick   = { color: "#8b949e", font: { size: 10 } };
    const grid   = { color: "rgba(255,255,255,0.06)" };
    const base   = {
        plugins: { legend: { labels: { color: "#8b949e", font: { size: 11 } } } },
        scales:  { x: { ticks: tick, grid }, y: { ticks: tick, grid } },
    };

    _dbRevenueChart = new Chart(document.getElementById("db-revenue-chart"), {
        type: "bar",
        data: { labels, datasets: [
            { label: "Baseline Revenue", data: projects.map(p => p.financials.baseline_rev),
              backgroundColor: "rgba(88,166,255,0.8)", borderRadius: 5 },
            { label: "Actual Cost",      data: projects.map(p => p.financials.actual_cost),
              backgroundColor: "rgba(248,113,113,0.75)", borderRadius: 5 },
        ]},
        options: { ...base, responsive: true, maintainAspectRatio: false },
    });

    const margins = projects.map(p => p.financials.margin_pct);
    _dbMarginChart = new Chart(document.getElementById("db-margin-chart"), {
        type: "bar",
        data: { labels, datasets: [{
            label: "Margin %",
            data: margins,
            backgroundColor: margins.map(m => m >= 20 ? "rgba(74,222,128,0.8)" : m >= 10 ? "rgba(251,191,36,0.8)" : "rgba(248,113,113,0.8)"),
            borderRadius: 5,
        }]},
        options: { ...base, responsive: true, maintainAspectRatio: false,
            scales: { ...base.scales, y: { ticks: { ...tick, callback: v => v + "%" }, grid } } },
    });
}

function dbKpiCard(label, value, sub, valCls, accentCls) {
    return dbEl("div", { className: "db-kpi-card " + (accentCls || "") }, [
        dbEl("div", { className: "db-kpi-label" }, [label]),
        dbEl("div", { className: "db-kpi-value " + (valCls || "") }, [value]),
        dbEl("div", { className: "db-kpi-sub" }, [sub]),
    ]);
}

let _dbProjects = [];
let _dbReport   = "";
let _dbProjectsContainer = null;  // div holding the project cards

// ─── Sort helpers ──────────────────────────────────────────────────────────
const STATUS_ORDER = { "AT RISK": 0, "DELAYED": 1, "ON TRACK": 2 };

function _daysRemaining(p) {
    const d = Date.parse(p.end_date);
    return isNaN(d) ? Infinity : Math.round((d - Date.now()) / 86_400_000);
}

function dbSortProjects(projects, key) {
    const sorted = [...projects];
    switch (key) {
        case "status":
            sorted.sort((a, b) => {
                const sa = STATUS_ORDER[(a.stage || "").toUpperCase()] ?? 3;
                const sb = STATUS_ORDER[(b.stage || "").toUpperCase()] ?? 3;
                return sa !== sb ? sa - sb : a.customer.localeCompare(b.customer);
            });
            break;
        case "days":
            sorted.sort((a, b) => _daysRemaining(a) - _daysRemaining(b));
            break;
        case "revenue":
            sorted.sort((a, b) => b.financials.baseline_rev - a.financials.baseline_rev);
            break;
        case "loss":
            sorted.sort((a, b) => a.financials.rev_variance - b.financials.rev_variance);
            break;
    }
    return sorted;
}

function dbRenderProjectCards(projects, report) {
    if (!_dbProjectsContainer) return;
    const sortKey = document.getElementById("db-sort-select")?.value || "status";
    const sorted  = dbSortProjects(projects, sortKey);
    const cards   = sorted.map((p, i) => dbProjectCard(p, i, report));
    const hdr = dbEl("div", { className: "db-section-hdr" }, [
        dbEl("div", { className: "db-section-title" }, ["Projects (" + projects.length + ")"]),
    ]);
    _dbProjectsContainer.replaceChildren(hdr, ...cards);
}

async function loadDashboard() {
    const btn = document.getElementById("db-refresh-btn");
    const app = document.getElementById("db-app");
    if (!btn || !app) return;

    btn.disabled = true;
    btn.textContent = "\u21BB Loading\u2026";
    app.replaceChildren(dbEl("div", { className: "db-loading" }, [
        dbEl("div", { className: "db-spinner" }, []),
        dbEl("span", {}, ["Generating portfolio report\u2026"]),
    ]));

    try {
        const res = await fetch("http://localhost:8000/dashboard");
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data     = await res.json();
        _dbProjects    = data.projects || [];
        _dbReport      = data.report   || "";
        const report   = _dbReport;

        const now  = new Date();
        const h12  = now.getHours() % 12 || 12;
        const ampm = now.getHours() < 12 ? "AM" : "PM";
        const time = String(h12).padStart(2, "0") + ":" + String(now.getMinutes()).padStart(2, "0") + " " + ampm;
        const dateEl = document.getElementById("db-report-date");
        if (dateEl) dateEl.textContent = "Updated: " + dbFmtDate(now) + ", " + time;

        const currency  = _dbProjects[0]?.financials?.currency || "SGD";
        const totalRev  = _dbProjects.reduce((s, p) => s + (p.financials.baseline_rev || 0), 0);
        const totalCost = _dbProjects.reduce((s, p) => s + (p.financials.actual_cost  || 0), 0);
        const totalVar  = totalRev - totalCost;
        const avgMargin = _dbProjects.length ? _dbProjects.reduce((s, p) => s + p.financials.margin_pct, 0) / _dbProjects.length : 0;
        const atRisk    = _dbProjects.filter(p => ["AT RISK","DELAYED"].includes((p.stage || "").toUpperCase())).length;
        const highRaids = _dbProjects.reduce((s, p) => s + p.raids.high, 0);
        const openRaids = _dbProjects.reduce((s, p) => s + p.raids.open, 0);

        const kpiRow = dbEl("div", { className: "db-kpi-row" }, [
            dbKpiCard("Total Projects",    String(_dbProjects.length), atRisk + " at risk / delayed",           "",           atRisk > 0 ? "accent-yellow" : "accent-green"),
            dbKpiCard("Portfolio Revenue", dbFmtCurrency(totalRev, currency), "Baseline across all projects",   "db-kpi-pos", "accent-green"),
            dbKpiCard("Revenue Variance",  dbFmtCurrency(totalVar, currency), "Avg margin: " + avgMargin.toFixed(1) + "%", totalVar >= 0 ? "db-kpi-pos" : "db-kpi-neg", totalVar >= 0 ? "accent-green" : "accent-red"),
            dbKpiCard("High RAID Items",   String(highRaids), openRaids + " open total",                        highRaids > 0 ? "db-kpi-neg" : "db-kpi-pos", highRaids > 0 ? "accent-red" : "accent-green"),
        ]);

        const revCanvas = dbEl("canvas", { id: "db-revenue-chart" }, []);
        const marCanvas = dbEl("canvas", { id: "db-margin-chart"  }, []);
        const chartsRow = dbEl("div", { className: "db-charts-row" }, [
            dbEl("div", { className: "db-chart-card" }, [dbEl("h3", {}, ["Revenue vs Cost by Project"]), dbEl("div", { className: "db-chart-wrap" }, [revCanvas])]),
            dbEl("div", { className: "db-chart-card" }, [dbEl("h3", {}, ["Margin % by Project"]),        dbEl("div", { className: "db-chart-wrap" }, [marCanvas])]),
        ]);

        _dbProjectsContainer = dbEl("div", {}, []);
        app.replaceChildren(kpiRow, chartsRow, _dbProjectsContainer);
        dbRenderProjectCards(_dbProjects, report);
        dbRenderCharts(_dbProjects);

        // Wire top-bar buttons (they live outside db-app, so wire after render)
        const expandBtn  = document.getElementById("db-expand-all-btn");
        const csvBtn     = document.getElementById("db-csv-btn");
        const pdfBtn     = document.getElementById("db-pdf-btn");
        const sortSelect = document.getElementById("db-sort-select");

        let allExpanded = false;
        expandBtn.onclick = () => {
            allExpanded = !allExpanded;
            _dbProjectsContainer.querySelectorAll(".db-project-card").forEach(c => c.classList.toggle("open", allExpanded));
            expandBtn.textContent = allExpanded ? "Collapse All" : "Expand All";
        };
        sortSelect.onchange = () => dbRenderProjectCards(_dbProjects, report);
        csvBtn.onclick = () => dbExportCSV(_dbProjects);
        pdfBtn.onclick = () => dbExportPDF(_dbProjects, report);

    } catch (err) {
        app.replaceChildren(dbEl("div", { className: "db-error" }, [
            "\u274C Failed to load dashboard: " + err.message,
            dbEl("br", {}, []),
            "Make sure the orchestrator is running on port 8000.",
        ]));
    }

    btn.disabled = false;
    btn.textContent = "\u21BB Refresh";
}

document.getElementById("db-refresh-btn")?.addEventListener("click", loadDashboard);
