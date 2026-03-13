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

A production-ready, locally-runnable multi-agent AI system for project portfolio management. Combines LangGraph orchestration, Groq LLM, ChromaDB RAG, and a SQLite structured database to answer natural-language queries about projects, contracts, risks, and financials.

## Architecture

```
User
 ↓
Chat UI  (ui/index.html)         Portfolio Dashboard  (ui/dashboard.html)
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
 ├── MBR Agent                (portfolio dashboard + recovery plans)
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

This starts all 3 services and prints the URLs:

| Service | URL |
|---|---|
| Chat UI | http://localhost:3000 |
| Portfolio Dashboard | http://localhost:3000/dashboard.html |
| API docs | http://localhost:8000/docs |
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
| Add/update/resolve a RAID item | **RAID Update Agent** |
| Pricing, cost breakdown | **Pricing Agent** |
| Portfolio overview, MBR report | **MBR Agent** |
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

# Portfolio
"Show me the portfolio dashboard"
"Which projects are over budget?"
"Generate an MBR report with recovery plans"
```

---

## Portfolio Dashboard

The dashboard (`ui/dashboard.html`) provides:
- **KPI cards** — total projects, portfolio revenue, variance, high RAID count
- **Charts** — Revenue vs Cost and Margin % per project (Chart.js)
- **Project cards** — colour-coded by status with expandable RAID table and recovery plan
  - 🟢 ON TRACK — green left border
  - 🟠 DELAYED — orange left border
  - 🔴 AT RISK — red left border
- Auto-expands at-risk and delayed projects on load

Served at `http://localhost:3000/dashboard.html`. Fetches live data from `GET /dashboard` on the orchestrator.

---

## Project Structure

```
Projectagent/
├── ui/
│   ├── index.html           # Chat UI
│   ├── dashboard.html       # Portfolio dashboard
│   ├── style.css            # Chat UI styles
│   └── app.js               # Chat UI logic
├── runtime/
│   └── gateway/server.js    # Node.js HTTP gateway + static file server
├── orchestrator/
│   ├── main.py              # FastAPI app + /chat, /ingest, /dashboard endpoints
│   ├── graph.py             # LangGraph StateGraph (agent wiring)
│   ├── router.py            # Dynamic router node
│   ├── acp_client.py        # ACP v1 client
│   ├── state.py             # AgentState TypedDict
│   └── llm_factory.py       # Groq LLM factory
├── agents/
│   ├── acp_agent_server.py  # ACP server — all agents as HTTP endpoints (port 8100)
│   ├── forecast_agent.py    # Plan-Forecast Agent
│   ├── contract_agent.py    # Contract Agent
│   ├── general_agent.py     # General Agent
│   ├── synthesizer.py       # Synthesizer (multi-agent merge)
│   ├── risk_agent.py        # Risk Agent
│   ├── raid_update_agent.py # RAID Update Agent
│   ├── pricing_agent.py     # Pricing Agent
│   ├── delete_project_agent.py
│   ├── mbr_agent.py         # MBR / Portfolio Agent
│   └── sql_agent.py         # Text-to-SQL Agent
├── tools/
│   ├── ingestion.py         # Document ingestion → ChromaDB
│   ├── retrieval.py         # ChromaDB similarity search
│   └── daily_report.py      # CLI script for scheduled MBR reports
├── data/
│   ├── openclaw.db          # SQLite — Projects, RAIDitems, WorkPackages
│   ├── chroma_db/           # Auto-created vector store
│   └── *.docx / *.xlsx      # Source documents for ingestion
├── start.sh                 # One-command launcher
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
