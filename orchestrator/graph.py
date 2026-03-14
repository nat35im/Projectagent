"""
LangGraph Orchestrator – StateGraph with ACP agent calls.

Flow:
  router_node
      ↓ (conditional edges)
  ┌───┴───────────────┐
  │                   │
  forecast-agent   contract-agent   general-agent
  (via ACP)        (via ACP)        (via ACP)
  └────────┬──────────┘
      synthesizer
      (via ACP)
          ↓
         END

Each specialist call goes through the ACP client → ACP Agent Server (port 8100).
Falls back to direct Python call if ACP server is unavailable.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langgraph.graph import StateGraph, END
from orchestrator.state import AgentState
from orchestrator.router import router_node
from orchestrator.acp_client import _call_acp_agent, acp_server_healthy

# Direct imports as fallback when ACP server is down
from agents.forecast_agent import forecast_agent_node as _forecast_direct
from agents.contract_agent import contract_agent_node as _contract_direct
from agents.general_agent import general_agent_node as _general_direct
from agents.synthesizer import synthesizer_node as _synthesizer_direct
from agents.delete_project_agent import delete_project_agent_node as _delete_project_direct
from agents.pricing_agent import pricing_agent_node as _pricing_direct
from agents.risk_agent import risk_agent_node as _risk_direct
from agents.raid_update_agent import raid_update_agent_node as _raid_update_direct
from agents.sql_agent import sql_agent_node as _sql_direct
from agents.mbr_agent import mbr_agent_node as _mbr_direct
from agents.document_viewer_agent import document_viewer_agent_node as _doc_viewer_direct

_ACP_AVAILABLE: bool | None = None   # cached after first check


def _use_acp() -> bool:
    global _ACP_AVAILABLE
    if _ACP_AVAILABLE is None:
        _ACP_AVAILABLE = acp_server_healthy()
        mode = "ACP" if _ACP_AVAILABLE else "direct (ACP server offline)"
        print(f"🔌 Agent call mode: {mode}")
    return _ACP_AVAILABLE


# ── ACP-enabled agent wrappers ─────────────────────────────────────────────

def forecast_agent_node(state: AgentState) -> dict:
    if _use_acp():
        text = _call_acp_agent("plan-forecast-agent", state["query"], history=state.get("history"))
        current = state.get("agent_outputs", [])
        debug   = state.get("debug_log", "")
        return {
            "agent_outputs": current + [f"--- Plan-Forecast Agent Report (ACP) ---\n{text}\n"],
            "debug_log":     debug + "\n✅ Plan-Forecast Agent: answered via ACP.",
        }
    return _forecast_direct(state)


def contract_agent_node(state: AgentState) -> dict:
    if _use_acp():
        text = _call_acp_agent("contract-agent", state["query"], history=state.get("history"))
        current = state.get("agent_outputs", [])
        debug   = state.get("debug_log", "")
        return {
            "agent_outputs": current + [f"--- Contract Agent Report (ACP) ---\n{text}\n"],
            "debug_log":     debug + "\n✅ Contract Agent: answered via ACP.",
        }
    return _contract_direct(state)


def general_agent_node(state: AgentState) -> dict:
    if _use_acp():
        text  = _call_acp_agent("general-agent", state["query"], history=state.get("history"))
        debug = state.get("debug_log", "")
        return {
            "response":  text,
            "debug_log": debug + "\n💬 General Agent: free-form response via ACP.",
        }
    return _general_direct(state)


def delete_project_agent_node(state: AgentState) -> dict:
    if _use_acp():
        text = _call_acp_agent("delete-project-agent", state["query"], history=state.get("history"))
        debug = state.get("debug_log", "")
        return {
            "response": text,
            "debug_log": debug + "\n🗑️ Delete Project Agent: processed via ACP.",
        }
    return _delete_project_direct(state)


def pricing_agent_node(state: AgentState) -> dict:
    if _use_acp():
        text = _call_acp_agent("pricing-agent", state["query"], history=state.get("history"))
        debug = state.get("debug_log", "")
        return {
            "response": text,
            "debug_log": debug + "\n💰 Pricing Agent: processed via ACP.",
        }
    return _pricing_direct(state)


def risk_agent_node(state: AgentState) -> dict:
    if _use_acp():
        text = _call_acp_agent("risk-agent", state["query"], history=state.get("history"))
        debug = state.get("debug_log", "")
        return {
            "response": text,
            "debug_log": debug + "\n⚠️ Risk Agent: processed via ACP.",
        }
    return _risk_direct(state)


def raid_update_agent_node(state: AgentState) -> dict:
    if _use_acp():
        text = _call_acp_agent("raid-update-agent", state["query"], history=state.get("history"))
        debug = state.get("debug_log", "")
        return {
            "response": text,
            "debug_log": debug + "\n⚡ RAID Update Agent: processed via ACP.",
        }
    return _raid_update_direct(state)


def mbr_agent_node(state: AgentState) -> dict:
    if _use_acp():
        text = _call_acp_agent("mbr-agent", state["query"], history=state.get("history"))
        debug = state.get("debug_log", "")
        return {
            "response": text,
            "debug_log": debug + "\n📊 MBR Agent: portfolio report via ACP.",
        }
    return _mbr_direct(state)


def document_viewer_agent_node(state: AgentState) -> dict:
    # Document Viewer always runs directly — no ACP wrapper needed (read-only, local files).
    return _doc_viewer_direct(state)


def sql_agent_node(state: AgentState) -> dict:
    # SQL Agent manages its own next_node decision and SQLite execution.
    # We call it directly to ensure the state machine routes correctly.
    return _sql_direct(state)


def synthesizer_node(state: AgentState) -> dict:
    if _use_acp():
        outputs = state.get("agent_outputs", [])
        text    = _call_acp_agent("synthesizer-agent", state["query"], outputs, history=state.get("history"))
        debug   = state.get("debug_log", "")
        return {
            "response":  text,
            "debug_log": debug + "\n🤖 Synthesizer: merged via ACP.",
        }
    return _synthesizer_direct(state)


# ── Conditional edge ───────────────────────────────────────────────────────

def _route_decision(state: AgentState):
    decision = state["next_node"]
    if decision == "both":
        return ["plan-forecast_agent", "contract_agent"]
    if decision == "plan-forecast_agent":
        return ["plan-forecast_agent"]
    if decision == "contract_agent":
        return ["contract_agent"]
    if decision == "delete_agent":
        return ["delete_agent"]
    if decision == "pricing_agent":
        return ["pricing_agent"]
    if decision == "risk_agent":
        return ["risk_agent"]
    if decision == "raid_update_agent":
        return ["raid_update_agent"]
    if decision == "mbr_agent":
        return ["mbr_agent"]
    if decision == "document_viewer_agent":
        return ["document_viewer_agent"]
    return ["general_agent"]


def _sql_decision(state: AgentState):
    decision = state.get("next_node")
    if decision == "router":
        return "router"
    return "END"


# ── Build Graph ────────────────────────────────────────────────────────────

def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("router",               router_node)
    workflow.add_node("sql_agent",            sql_agent_node)
    workflow.add_node("plan-forecast_agent",  forecast_agent_node)
    workflow.add_node("contract_agent",       contract_agent_node)
    workflow.add_node("general_agent", general_agent_node)
    workflow.add_node("synthesizer", synthesizer_node)
    workflow.add_node("delete_agent", delete_project_agent_node)
    workflow.add_node("pricing_agent", pricing_agent_node)
    workflow.add_node("risk_agent", risk_agent_node)
    workflow.add_node("raid_update_agent", raid_update_agent_node)
    workflow.add_node("mbr_agent", mbr_agent_node)
    workflow.add_node("document_viewer_agent", document_viewer_agent_node)

    # All queries hit the Text-to-SQL logic first
    workflow.set_entry_point("sql_agent")
    
    # Text-to-SQL either answers the question directly or falls back to the RAG router
    workflow.add_conditional_edges(
        "sql_agent",
        _sql_decision,
        {
            "router": "router",
            "END": END
        }
    )

    # If falling back, the RAG Router takes over
    workflow.add_conditional_edges(
        "router",
        _route_decision,
        {
            "plan-forecast_agent": "plan-forecast_agent",
            "contract_agent": "contract_agent",
            "general_agent": "general_agent",
            "delete_agent": "delete_agent",
            "pricing_agent": "pricing_agent",
            "risk_agent": "risk_agent",
            "raid_update_agent": "raid_update_agent",
            "mbr_agent": "mbr_agent",
            "document_viewer_agent": "document_viewer_agent",
        }
    )

    workflow.add_edge("plan-forecast_agent", "synthesizer")
    workflow.add_edge("contract_agent", "synthesizer")
    workflow.add_edge("synthesizer", END)
    workflow.add_edge("general_agent", END)
    workflow.add_edge("delete_agent", END)
    workflow.add_edge("pricing_agent", END)
    workflow.add_edge("risk_agent", END)
    workflow.add_edge("raid_update_agent", END)
    workflow.add_edge("mbr_agent", END)
    workflow.add_edge("document_viewer_agent", END)

    return workflow.compile()


app = build_graph()
