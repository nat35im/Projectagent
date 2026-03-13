"""
ACP Agent Server – runs all specialist agents as ACP-compliant HTTP endpoints.

Architecture:
  LangGraph Orchestrator (ACP Client)
       ↓  ACP REST  (POST /runs)
  This server (port 8100)
       ├── /agents/plan-forecast-agent
       ├── /agents/contract-agent
       ├── /agents/general-agent
       └── /agents/synthesizer-agent

Wire format follows ACP v1 spec:
  POST /runs  { agent_name, input: [Message{parts:[MessagePart{content}]}] }
  → 200       { status, output: [Message{parts:[MessagePart{content}]}] }

Also exposes:
  GET  /agents           → list of AgentManifest
  GET  /agents/{name}    → single AgentManifest
  GET  /.well-known/agent.json  → A2A Agent Card (root agent)
"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv
import uvicorn, uuid

load_dotenv()

# ── Local imports ──────────────────────────────────────────────────────────
from agents.forecast_agent import forecast_agent_node
from agents.contract_agent import contract_agent_node
from agents.general_agent import general_agent_node
from agents.synthesizer import synthesizer_node
from agents.delete_project_agent import delete_project_agent_node
from agents.pricing_agent import pricing_agent_node
from agents.risk_agent import risk_agent_node
from agents.raid_update_agent import raid_update_agent_node
from agents.sql_agent import sql_agent_node
from agents.mbr_agent import mbr_agent_node

ACP_PORT = int(os.getenv("ACP_PORT", "8100"))

# ── ACP Wire-format models (subset of ACP v1) ─────────────────────────────
class AcpMessagePart(BaseModel):
    content_type: str = "text/plain"
    content: str

class AcpMessage(BaseModel):
    parts: List[AcpMessagePart]

class AcpRunRequest(BaseModel):
    agent_name: str
    input: List[AcpMessage]
    session_id: Optional[str] = None

class AcpRunResponse(BaseModel):
    run_id: str
    agent_name: str
    status: str      # "completed" | "failed"
    output: List[AcpMessage]

class AcpAgentManifest(BaseModel):
    name: str
    description: str
    input_content_types: List[str] = ["text/plain"]
    output_content_types: List[str] = ["text/plain"]

# ── Agent registry ─────────────────────────────────────────────────────────
AGENT_REGISTRY: dict[str, dict] = {
    "plan-forecast-agent": {
        "name": "plan-forecast-agent",
        "description": "Answers questions about project planning, schedules, resources, and hours capacity.",
        "handler": lambda q, outputs, history, debug: forecast_agent_node({
            "query": q, "agent_outputs": outputs, "history": history, "debug_log": debug,
            "response": "", "next_node": "",
        }),
    },
    "contract-agent": {
        "name": "contract-agent",
        "description": "Answers questions about SOWs, statements of work, and formal deliverables.",
        "handler": lambda q, outputs, history, debug: contract_agent_node({
            "query": q, "agent_outputs": outputs, "history": history, "debug_log": debug,
            "response": "", "next_node": "",
        }),
    },
    "general-agent": {
        "name": "general-agent",
        "description": "Handles general conversational queries unrelated to specialized project data.",
        "handler": lambda q, outputs, history, debug: general_agent_node({
            "query": q, "agent_outputs": outputs, "history": history, "debug_log": debug,
            "response": "", "next_node": "",
        }),
    },
    "synthesizer-agent": {
        "name": "synthesizer-agent",
        "description": "Merges outputs from multiple agents into a coherent final response.",
        "handler": lambda q, outputs, history, debug: synthesizer_node({
            "query": q, "agent_outputs": outputs, "history": history, "debug_log": debug,
            "response": "", "next_node": "",
        }),
    },
    "delete-project-agent": {
        "name": "delete-project-agent",
        "description": "Agent responsible for deleting projects from the database based on Project Number or Opportunity ID.",
        "handler": lambda q, outputs, history, debug: delete_project_agent_node({
            "query": q, "agent_outputs": outputs, "history": history, "debug_log": debug,
            "response": "", "next_node": "",
        }),
    },
    "pricing-agent": {
        "name": "pricing-agent",
        "description": "Extracts pricing and payment schedules from the DB or RAG. Highly specialized for contracts and SOWs.",
        "handler": lambda q, outputs, history, debug: pricing_agent_node({
            "query": q, "agent_outputs": outputs, "history": history, "debug_log": debug,
            "response": "", "next_node": "",
        }),
    },
    "risk-agent": {
        "name": "risk-agent",
        "description": "Extracts contract and operational risk analysis from the RAID log, Work Packages, or RAG.",
        "handler": lambda q, outputs, history, debug: risk_agent_node({
            "query": q, "agent_outputs": outputs, "history": history, "debug_log": debug,
            "response": "", "next_node": "",
        }),
    },
    "raid-update-agent": {
        "name": "raid-update-agent",
        "description": "Updates or creates operational RAID (Risk, Action, Issue, Decision) items using natural language.",
        "handler": lambda q, outputs, history, debug: raid_update_agent_node({
            "query": q, "agent_outputs": outputs, "history": history, "debug_log": debug,
            "response": "", "next_node": "",
        }),
    },
    "sql-agent": {
        "name": "sql-agent",
        "description": "Primary Text-to-SQL logic agent mapping query to structured project database schema.",
        "handler": lambda q, outputs, history, debug: sql_agent_node({
            "query": q, "agent_outputs": outputs, "history": history, "debug_log": debug,
            "response": "", "next_node": "",
        }),
    },
    "mbr-agent": {
        "name": "mbr-agent",
        "description": "Generates a portfolio MBR dashboard: project status, revenue/loss forecast, RAID summary, and recovery plan for all projects.",
        "handler": lambda q, outputs, history, debug: mbr_agent_node({
            "query": q, "agent_outputs": outputs, "history": history, "debug_log": debug,
            "response": "", "next_node": "",
        }),
    },
}

# ── FastAPI App ────────────────────────────────────────────────────────────
app = FastAPI(
    title="OpenClaw ACP Agent Server",
    description="ACP-compliant multi-agent server for the OpenClaw system",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/agents", response_model=List[AcpAgentManifest])
def list_agents():
    return [
        AcpAgentManifest(name=name, description=meta["description"])
        for name, meta in AGENT_REGISTRY.items()
    ]


@app.get("/agents/{agent_name}", response_model=AcpAgentManifest)
def get_agent(agent_name: str):
    if agent_name not in AGENT_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")
    meta = AGENT_REGISTRY[agent_name]
    return AcpAgentManifest(name=agent_name, description=meta["description"])


@app.post("/runs", response_model=AcpRunResponse)
def create_run(req: AcpRunRequest):
    """
    ACP v1 /runs endpoint.
    The orchestrator posts here with { agent_name, input: [Message] }.
    We invoke the corresponding agent node and return the result.
    """
    agent_name = req.agent_name
    if agent_name not in AGENT_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")

    # Extract text query from the first message part
    query = ""
    agent_outputs: list[str] = []
    history: list[dict] = []
    for msg in req.input:
        for part in msg.parts:
            if part.content_type == "text/plain":
                query += part.content + "\n"
            elif part.content_type == "application/json":
                import json
                try:
                    data = json.loads(part.content)
                    # Heuristic: if it's a list, check if it's history or agent_outputs
                    if isinstance(data, list):
                        if any(isinstance(item, dict) and "role" in item for item in data):
                            history = data
                        else:
                            agent_outputs = data
                except Exception:
                    pass
    query = query.strip()

    try:
        handler = AGENT_REGISTRY[agent_name]["handler"]
        result = handler(query, agent_outputs, history, "")
        # Collect the output text
        if "response" in result and result["response"]:
            text = result["response"]
        elif "agent_outputs" in result and result["agent_outputs"]:
            text = "\n".join(result["agent_outputs"])
        else:
            text = "No output."

        output_msg = AcpMessage(parts=[AcpMessagePart(content=text)])
        return AcpRunResponse(
            run_id=str(uuid.uuid4()),
            agent_name=agent_name,
            status="completed",
            output=[output_msg],
        )
    except Exception as exc:
        err_msg = AcpMessage(parts=[AcpMessagePart(content=f"Agent error: {exc}")])
        return AcpRunResponse(
            run_id=str(uuid.uuid4()),
            agent_name=agent_name,
            status="failed",
            output=[err_msg],
        )


# ── A2A Agent Card (root agent) ────────────────────────────────────────────
@app.get("/.well-known/agent.json")
def a2a_agent_card():
    """Google A2A Agent Card – describes this ACP server to A2A clients."""
    host = os.getenv("ORCHESTRATOR_HOST", "localhost")
    return JSONResponse({
        "name": "openclaw-agent-mesh",
        "description": (
            "OpenClaw Multi-Agent System: routes queries to Plan-Forecast, "
            "Contract, General, or Synthesizer agents using ACP protocol."
        ),
        "version": "1.0.0",
        "url": f"http://{host}:{ACP_PORT}",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False,
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": name,
                "name": name,
                "description": meta["description"],
                "tags": ["rag", "project-management"],
                "examples": [],
            }
            for name, meta in AGENT_REGISTRY.items()
        ],
    })


if __name__ == "__main__":
    print(f"\n🤖 OpenClaw ACP Agent Server starting on port {ACP_PORT} …")
    uvicorn.run("acp_agent_server:app", host="0.0.0.0", port=ACP_PORT, reload=True)
