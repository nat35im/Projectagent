#!/usr/bin/env bash
set -e

echo "╔══════════════════════════════════════════════════╗"
echo "║        Project Agent v1 – Starting Up            ║"
echo "╚══════════════════════════════════════════════════╝"

# HF Spaces passes secrets as env vars; ensure paths are absolute
export CHROMA_DB_PATH=${CHROMA_DB_PATH:-/app/data/chroma_db}
export SOURCE_DATA_DIR=${SOURCE_DATA_DIR:-/app/data}
export SQLITE_DB_PATH=${SQLITE_DB_PATH:-/app/data/openclaw.db}
export ORCHESTRATOR_HOST=${ORCHESTRATOR_HOST:-localhost}
export ORCHESTRATOR_PORT=${ORCHESTRATOR_PORT:-8000}
export ACP_PORT=${ACP_PORT:-8100}
# HF Spaces expects the app on port 7860
export GATEWAY_PORT=7860

# ── Start FastAPI Orchestrator ────────────────────────────────────────────────
echo "🐍 Starting Python Orchestrator on port 8000…"
cd /app/orchestrator
python main.py &
PYTHON_PID=$!
sleep 5

# ── Start ACP Agent Server ────────────────────────────────────────────────────
echo "🤖 Starting ACP Agent Server on port 8100…"
cd /app/agents
python acp_agent_server.py &
ACP_PID=$!
sleep 3

# ── Start Node.js Gateway (foreground, port 7860) ────────────────────────────
echo "⚙️  Starting Node.js Gateway on port 7860…"
cd /app/runtime
exec node gateway/server.js
