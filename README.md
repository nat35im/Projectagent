---
title: Project Agent v1
emoji: 🤖
colorFrom: blue
colorTo: navy
sdk: docker
pinned: false
app_port: 7860
---

# Project Agent v1

A production-ready, locally-runnable multi-agent AI system for project portfolio management. Combines LangGraph orchestration, Groq LLM, ChromaDB RAG, and a SQLite structured database to answer natural-language queries about projects, contracts, risks, and financials — all from a single-page UI.

## Architecture

```
User
 ↓
Chat UI  (ui/index.html)
 ├── 💬 Chat tab
 ├── 📁 Create Project tab
 └── 📊 Dashboard tab  (integrated, no separate page)
 ↓ HTTP / REST
Node.js Gateway  (runtime/gateway/server.js)
 ↓
LangGraph Orchestrator  (orchestrator/)
 ↓
SQL Agent  ──── answers structured queries directly via SQLite
 ↓ (fallback to RAG router)
Router Node  ──── classifies query → specialist agent
 ├── Plan-Forecast Agent      (RAG: estimation/milestone docs)
 ├── Contract Agent           (RAG: SOW/contract docs)
 ├── Risk Agent               (RAID log + RAG)
 ├── RAID Update Agent        (write RAID items to DB)
 ├── Pricing Agent            (contract pricing + RAG)
 ├── Delete Project Agent     (remove project from DB)
 ├── MBR Agent                (portfolio overview + recovery plans)
 ├── Document Viewer Agent    (sandboxed read-only file viewer)
 ├── Both → Synthesizer       (multi-agent merge)
 └── General Agent            (free-form conversation)
 ↓
Tools  (tools/)
 ├── ChromaDB  (data/chroma_db/)      ← vector store
 ├── SQLite    (data/openclaw.db)     ← structured project data
 └── Groq LLM  (openai/gpt-oss-120b) ← language model

ACP Agent Server  (agents/acp_agent_server.py)  ← port 8100
 └── All agents registered as ACP v1 endpoints
```

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- A [Groq](https://console.groq.com) API key

### Run the app

```bash
cd /path/to/Projectagent
./start.sh
```

This starts all 3 services:

| Service | URL |
|---|---|
| Chat UI + Dashboard | http://localhost:3000 |
| Orchestrator API docs | http://localhost:8000/docs |
| ACP agents | http://localhost:8100/agents |

Press `Ctrl+C` to stop all services.

> First run: if `start.sh` is not executable, run `chmod +x start.sh` first.

### Manual start (alternative)

```bash
# Terminal 1 — Python orchestrator
cd orchestrator && python main.py

# Terminal 2 — ACP agent server
cd agents && python acp_agent_server.py

# Terminal 3 — Node.js gateway
cd runtime && node gateway/server.js
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | _(required)_ | Groq cloud API key |
| `EMBEDDING_MODEL` | `all-mpnet-base-v2` | HuggingFace embedding model |
| `CHROMA_DB_PATH` | `./data/chroma_db` | ChromaDB persistence path |
| `SOURCE_DATA_DIR` | `./data` | Document source folder for ingestion |
| `SQLITE_DB_PATH` | `./data/openclaw.db` | SQLite structured project database |
| `ORCHESTRATOR_PORT` | `8000` | FastAPI server port |
| `ACP_PORT` | `8100` | ACP agent server port |
| `GATEWAY_PORT` | `3000` | Node.js gateway port |

---

## Agent Routing

Every query hits the **SQL Agent** first. If the structured database can answer it, it returns directly. Otherwise it falls back to the **RAG Router**:

| Query intent | Agent |
|---|---|
| Project data, stages, costs, resources | **SQL Agent** (direct DB) |
| Planning, hours, forecast | **Plan-Forecast Agent** |
| Contracts, SOW, payment schedules | **Contract Agent** |
| Risk analysis, RAID log summary | **Risk Agent** |
| Add / update / resolve a RAID item | **RAID Update Agent** |
| Pricing, cost breakdown | **Pricing Agent** |
| Portfolio overview, MBR report | **MBR Agent** |
| View / read an uploaded document | **Document Viewer Agent** |
| Delete a project | **Delete Project Agent** |
| Both plan + contract (compare/synthesise) | **Both → Synthesizer** |
| General / off-topic | **General Agent** |

---

## Example Chat Queries

```
# Project data
"List all projects and their stage"
"What is the baseline revenue for the Changi Airport project?"
"Show me all AT RISK projects"

# Contracts & plans
"Give me the payment schedule for Boston Property"
"What are the key deliverables in the OCBC contract?"
"Compare the plan and contract for Standard Chartered"

# RAID
"What are the open risks for the Changi Airport project?"
"Add a new high risk for project 202024: key developer resigned. Owner: Kevin Lim."
"Resolve RAID-SCB-0001 — issue has been closed"

# Documents
"Show me the contract file for Boston Property"
"View the estimation Excel for DBS Bank"

# Portfolio
"Show me the portfolio dashboard"
"Which projects are over budget?"
"Generate an MBR report with recovery plans"
```

---

## Portfolio Dashboard

The dashboard is built into the main UI (`ui/index.html`) as a tab — no separate page needed.

**Features:**
- **KPI cards** — total projects, portfolio revenue, variance, open RAID count
- **Charts** — Revenue vs Cost and Margin % per project (Chart.js)
- **Project cards** — colour-coded by status, expandable RAID table and recovery plan
  - 🟢 ON TRACK — green left border
  - 🟠 DELAYED — orange left border
  - 🔴 AT RISK — red left border
- **Overdue RAID alert banner** — polls `/raid/alerts` every 30 seconds, shown on both Chat and Dashboard tabs
- **CSV export** — three-section report: portfolio summary, project detail, open RAID items
- **PDF export** — styled HTML report with KPIs, project cards, RAID tables, and recovery plans; opens in a new tab and triggers the browser print dialog

---

## Document Viewer Agent

The `document_viewer_agent` reads uploaded project documents (PDF, DOCX, XLSX) safely:

- **Sandboxed** — only reads files inside `data/docs/projects/`. Path traversal is blocked.
- **Read-only** — no writes, no modifications.
- **LLM-assisted** — the agent summarises or answers specific questions about the document content.
- Supports `.pdf` (via pdfplumber / pypdf), `.docx` / `.doc` (via python-docx), `.xlsx` / `.xls` (via openpyxl).

Trigger via chat: *"Show me the contract for Boston Property"* or *"View the estimation file for DBS"*.

---

## Database Schema (SQLite)

**`Project`** — core project metadata, financials, JSON blobs for SOW, resources, invoices, revenue, hours.

**`ProjectWorkPackage`** — per-phase work breakdown with scope, deliverables, acceptance criteria, and a `quick_summary` field.

**`RAIDitems`** — Risks, Actions, Issues, Decisions per project. Fields: `Type`, `Category` (High/Medium/Low), `owner`, `DueDate`, `ROAM`, `Status`, `Status_summary` (audit trail log).

**`ProjectWeeklySummary`** — weekly status snapshots with RAG ratings across 9 dimensions (Delivery, Financial, Schedule, Resource, etc.) plus ITD/EAC financials and recovery plan narrative.

**`MBRitems`** — MBR financial forecast entries (baseline, forecast amount, status).

---

## Project Structure

```
Projectagent/
├── ui/
│   ├── index.html           # Single-page UI: Chat, Create Project, Dashboard tabs
│   ├── style.css            # UI styles
│   └── app.js               # UI logic (chat, project creation, dashboard, exports)
├── runtime/
│   └── gateway/server.js    # Node.js HTTP gateway + static file server
├── orchestrator/
│   ├── main.py              # FastAPI app + /chat, /ingest, /dashboard, /raid/alerts
│   ├── graph.py             # LangGraph StateGraph (agent wiring)
│   ├── router.py            # Dynamic router node
│   ├── project_graph.py     # Project creation sub-graph
│   ├── acp_client.py        # ACP v1 client
│   ├── state.py             # AgentState TypedDict
│   └── llm_factory.py       # Groq LLM factory
├── agents/
│   ├── acp_agent_server.py      # ACP server — all agents as HTTP endpoints (port 8100)
│   ├── sql_agent.py             # Text-to-SQL Agent (first responder)
│   ├── forecast_agent.py        # Plan-Forecast Agent
│   ├── contract_agent.py        # Contract Agent
│   ├── risk_agent.py            # Risk Agent
│   ├── raid_update_agent.py     # RAID Update Agent
│   ├── pricing_agent.py         # Pricing Agent
│   ├── mbr_agent.py             # MBR / Portfolio Agent
│   ├── document_viewer_agent.py # Document Viewer Agent (sandboxed, read-only)
│   ├── delete_project_agent.py  # Delete Project Agent
│   ├── general_agent.py         # General Agent
│   ├── synthesizer.py           # Synthesizer (multi-agent merge)
│   ├── ingestion_agent.py       # Document ingestion into ChromaDB
│   └── data_extraction_agent.py # Structured data extraction for project creation
├── tools/
│   ├── ingestion.py         # Document ingestion → ChromaDB
│   ├── retrieval.py         # ChromaDB similarity search
│   ├── excel_parser.py      # Estimation/milestone Excel parser
│   └── daily_report.py      # CLI script for scheduled MBR reports
├── data/
│   ├── openclaw.db          # SQLite — Projects, RAIDitems, WorkPackages, WeeklySummary
│   ├── chroma_db/           # Auto-created vector store
│   └── docs/projects/       # Uploaded project documents (per project subfolder)
├── start.sh                 # One-command launcher
├── Dockerfile               # Docker image for HuggingFace Spaces deployment
├── .env                     # Local config (not committed)
├── .env.example             # Config template
└── requirements.txt
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Groq Cloud — `openai/gpt-oss-120b` |
| Orchestration | LangGraph StateGraph |
| Agent protocol | ACP v1 (Agent Communication Protocol) |
| Vector store | ChromaDB (local persistent) |
| Embeddings | HuggingFace `all-mpnet-base-v2` |
| Structured DB | SQLite |
| API | FastAPI (Python) |
| Gateway | Node.js / Express |
| UI | Vanilla HTML/CSS/JS + Chart.js |
| PDF export | Browser print via Blob URL |
