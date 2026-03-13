"""
Router node: dynamically discovers what each collection covers, then
classifies the user query into one of the available agent buckets.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orchestrator.state import AgentState
from orchestrator.llm_factory import get_llm
from tools.retrieval import list_collections
from langchain_core.messages import SystemMessage, HumanMessage

llm = get_llm()

# Holds discovered topic descriptions per collection stem
ROUTER_CONTEXT: dict[str, str] = {}

# Map collection stem → agent key used in the graph
COLLECTION_TO_AGENT = {
    "plan-forecast": "plan-forecast_agent",
    "contract": "contract_agent",
    "estimation-milestone": "plan-forecast_agent",
    "project": "general_agent",
}


def _collection_stem(collection_name: str) -> str:
    """Strip '_collection' suffix."""
    return collection_name.replace("_collection", "")


def discover_collection_topics(collection_name: str, limit: int = 5) -> str:
    """Peek at a few documents and ask the LLM to summarise what this
    collection can answer."""
    import chromadb

    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env_val = os.getenv("CHROMA_DB_PATH", "./data/chroma_db")
    db_path = env_val if os.path.isabs(env_val) else os.path.abspath(os.path.join(PROJECT_ROOT, env_val))
    try:
        client = chromadb.PersistentClient(path=db_path)
        col = client.get_collection(collection_name)
        data = col.get(limit=limit, include=["documents"])
        docs = data["documents"]

        if not docs:
            return "No documents found."

        snippets = "\n---\n".join(docs)
        prompt = (
            f"Here are {len(docs)} sample snippets from a document collection. "
            "Summarise in ONE sentence what kind of questions this collection can answer. "
            "Be specific about topics, locations, or entities mentioned.\n\n"
            f"Snippets:\n{snippets}"
        )
        response = llm.invoke([SystemMessage(content=prompt)])
        return response.content.strip()
    except Exception as exc:
        return f"Collection discovery error: {exc}"


def initialize_router():
    """Discover topics for every collection in the vector store."""
    global ROUTER_CONTEXT
    print("🕵️  Discovering agent topics …")

    for col_name in list_collections():
        stem = _collection_stem(col_name)
        topic = discover_collection_topics(col_name)
        ROUTER_CONTEXT[stem] = topic
        agent_key = COLLECTION_TO_AGENT.get(stem, stem + "_agent")
        print(f"   📋 {agent_key}: {topic}")


def _build_router_prompt() -> str:
    buckets = []
    for i, (stem, description) in enumerate(ROUTER_CONTEXT.items(), 1):
        agent_key = COLLECTION_TO_AGENT.get(stem, stem + "_agent")
        buckets.append(f"{i}. '{agent_key}': {description}")

    next_i = len(ROUTER_CONTEXT) + 1
    buckets.append(
        f"{next_i}. 'both': Use ONLY when the query explicitly asks to "
        "compare, synthesise, or combine info from BOTH specialized agents."
    )
    buckets.append(
        f"{next_i + 1}. 'delete_agent': Use ONLY when the query explicitly asks to delete or remove a project."
    )
    buckets.append(
        f"{next_i + 2}. 'pricing_agent': Use ONLY when the query explicitly asks for pricing, cost, or a payment schedule."
    )
    buckets.append(
        f"{next_i + 3}. 'risk_agent': Use ONLY when the query explicitly asks for a general risk analysis, RAID log summary, or risk matrix."
    )
    buckets.append(
        f"{next_i + 4}. 'raid_update_agent': Use ONLY when the query explicitly instructs to ADD, CREATE, UPDATE, ASSIGN, or RESOLVE a specific risk, issue, action, or assumption, OR when reporting a missing PO (Purchase Order)."
    )
    buckets.append(
        f"{next_i + 5}. 'mbr_agent': Use when the query asks for a portfolio overview, dashboard, MBR report, all-projects status, recovery plan, revenue/loss summary, or forecast across all projects."
    )
    buckets.append(
        f"{next_i + 6}. 'general_agent': General conversation, off-topic, or greetings."
    )

    return (
        "You are a Router. Classify the user query into EXACTLY one of:\n\n"
        + "\n".join(buckets)
        + "\n\nOutput ONLY the exact key shown above. No explanation."
    )


def router_node(state: AgentState) -> dict:
    query = state["query"]
    debug = state.get("debug_log", "")

    # Ensure topics have been discovered
    if not ROUTER_CONTEXT:
        initialize_router()

    router_prompt = _build_router_prompt()

    valid_keys = (
        [COLLECTION_TO_AGENT.get(s, s + "_agent") for s in ROUTER_CONTEXT]
        + ["both", "delete_agent", "pricing_agent", "risk_agent", "raid_update_agent", "mbr_agent", "general_agent"]
    )

    # 1. Prepare messages with history
    history = state.get("history", [])
    messages = [SystemMessage(content=router_prompt)]
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=f"PAST USER QUERY: {msg['content']}"))
        else:
            # We don't want to pass the full assistant response to the router as it's too long
            # Just a hint that the assistant replied
            messages.append(HumanMessage(content="PAST ASSISTANT RESPONSE: (Data provided above)"))
    
    messages.append(HumanMessage(content=f"CURRENT USER QUERY: {query}"))

    try:
        response = llm.invoke(messages)
        decision = response.content.strip().lower().strip(".'\"")
    except Exception:
        decision = "general_agent"

    if decision not in valid_keys:
        # Heuristic fallback
        q = query.lower()
        if "delete" in q or "remove" in q:
            decision = "delete_agent"
        elif "pricing" in q or "cost" in q or "payment" in q or "price" in q:
            decision = "pricing_agent"
        elif any(action in q for action in ["add a risk", "add an issue", "create risk", "new risk", "create issue", "update raid", "update risk", "update action", "assign risk", "po ", "purchase order"]):
            decision = "raid_update_agent"
        elif "risk" in q or "raid" in q or "mitigation" in q or "issue" in q:
            decision = "risk_agent"
        elif any(w in q for w in ["dashboard", "mbr", "portfolio", "status report", "recovery plan", "all projects", "all project"]):
            decision = "mbr_agent"
        elif "plan" in q or "forecast" in q or "hours" in q:
            decision = "plan-forecast_agent"
        elif "contract" in q or "sow" in q or "agreement" in q:
            decision = "contract_agent"
        else:
            decision = "general_agent"

    return {
        "next_node": decision,
        "debug_log": debug + f"\n🚦 Router → {decision}",
        "agent_outputs": [],
    }
