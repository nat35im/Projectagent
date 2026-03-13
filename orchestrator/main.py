"""
FastAPI server – exposes the LangGraph orchestrator over HTTP.
The Node.js OpenClaw Gateway proxies requests here.
"""
import sys
import os
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from orchestrator.graph import app as langgraph_app

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECTS_DIR = os.path.join(PROJECT_ROOT, "data", "docs", "projects")

server = FastAPI(
    title="OpenClaw – LangGraph Orchestrator",
    description=(
        "Multi-agent RAG system: User → Chat UI → Node Gateway → "
        "FastAPI → LangGraph Orchestrator → Agent Mesh → Tools → Groq (openai/gpt-oss-120b)"
    ),
    version="3.0.0",
)

server.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Chat models ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = "default"

# ── In-memory Session Store ────────────────────────────────────────────────
# session_id -> List[dict] (history)
SESSION_STORE: dict[str, List[dict]] = {}


class ChatResponse(BaseModel):
    response: str
    debug_log: str
    agent: str  # which agent(s) handled this


# ── Health ─────────────────────────────────────────────────────────────────

@server.get("/health")
def health():
    return {"status": "ok", "service": "openclaw-orchestrator"}


# ── Chat endpoint ──────────────────────────────────────────────────────────

@server.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    session_id = req.session_id or "default"
    history = SESSION_STORE.get(session_id, [])

    initial_state = {
        "query": req.query,
        "response": "",
        "next_node": "",
        "agent_outputs": [],
        "history": history,
        "debug_log": "",
    }

    try:
        result = langgraph_app.invoke(initial_state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Update history in session store
    new_response = result.get("response", "No response generated.")
    updated_history = history + [
        {"role": "user", "content": req.query},
        {"role": "assistant", "content": new_response}
    ]
    # Keep history at reasonable length
    SESSION_STORE[session_id] = updated_history[-20:]

    debug = result.get("debug_log", "")
    agent_tag = "general_agent"
    for line in debug.splitlines():
        if "Router →" in line:
            agent_tag = line.split("Router →")[-1].strip()
            break

    return ChatResponse(
        response=new_response,
        debug_log=debug,
        agent=agent_tag,
    )


# ── Document ingestion ────────────────────────────────────────────────────

@server.post("/ingest")
def ingest():
    """Trigger re-ingestion of documents from SOURCE_DATA_DIR."""
    from tools.ingestion import build_knowledge_base
    collections = build_knowledge_base()
    return {"status": "ok", "indexed": collections}


# ── Project Creation: Phase A (upload → extract) ──────────────────────────

@server.post("/project/create")
async def create_project(
    project_name: str = Form(...),
    project_code: str = Form(...),
    opportunity_id: str = Form(""),
    contract_file: UploadFile = File(...),
    estimation_file: UploadFile = File(...),
    erp_file: UploadFile = File(None),
):
    """
    Upload contract + estimation-milestone (+ optional ERP) files,
    ingest into ChromaDB, and extract structured project data for user confirmation.
    The opportunity_id is optional — it can be extracted from the contract .docx.
    """
    from fastapi import HTTPException

    # ── Validate file types for each collection ──────────────────────────────
    VALID_CONTRACT_EXT = {".docx", ".doc", ".pdf"}
    VALID_EXCEL_EXT = {".xlsx", ".xls"}

    contract_ext = os.path.splitext(contract_file.filename)[1].lower()
    if contract_ext not in VALID_CONTRACT_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Contract file must be {', '.join(VALID_CONTRACT_EXT)}. Got: '{contract_ext}'"
        )

    estimation_ext = os.path.splitext(estimation_file.filename)[1].lower()
    if estimation_ext not in VALID_EXCEL_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Estimation-Milestone file must be {', '.join(VALID_EXCEL_EXT)}. Got: '{estimation_ext}'"
        )

    if erp_file and erp_file.filename:
        erp_ext = os.path.splitext(erp_file.filename)[1].lower()
        if erp_ext not in VALID_EXCEL_EXT:
            raise HTTPException(
                status_code=400,
                detail=f"ERP/Project file must be {', '.join(VALID_EXCEL_EXT)}. Got: '{erp_ext}'"
            )

    # 1. Save uploaded files to data/docs/projects/<project_code>/
    safe_code = project_code.replace(" ", "_").replace("-", "_").lower()
    project_dir = os.path.join(PROJECTS_DIR, safe_code)
    os.makedirs(project_dir, exist_ok=True)

    saved_files = []
    uploads = [contract_file, estimation_file]
    if erp_file and erp_file.filename:
        uploads.append(erp_file)

    for upload in uploads:
        dest = os.path.join(project_dir, upload.filename)
        with open(dest, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        saved_files.append(dest)

    # 2. Run the extraction graph
    from orchestrator.project_graph import extraction_app

    initial_state = {
        "query": f"Create project: {project_name}",
        "response": "",
        "next_node": "",
        "agent_outputs": [],
        "debug_log": "",
        "project_name": project_name,
        "project_code": project_code,
        "opportunity_id": opportunity_id,
        "uploaded_files": saved_files,
        "extracted_data": None,
        "user_confirmed": False,
        "operation_mode": "create_project",
        "collection_names": [],
    }

    try:
        result = extraction_app.invoke(initial_state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")

    extracted = result.get("extracted_data")
    if not extracted:
        raise HTTPException(
            status_code=422,
            detail="Could not extract project data. " + result.get("debug_log", ""),
        )

    return {
        "status": "pending_confirmation",
        "project_name": project_name,
        "project_code": project_code,
        "opportunity_id": opportunity_id,
        "extracted_data": extracted,
        "debug_log": result.get("debug_log", ""),
    }


# ── Project Creation: Phase B (confirm → persist) ────────────────────────

class ProjectConfirmRequest(BaseModel):
    project_name: str
    project_code: str
    opportunity_id: str
    extracted_data: dict


@server.post("/project/confirm")
def confirm_project(req: ProjectConfirmRequest):
    """
    Confirm the extracted data and persist to the database.
    The user may have edited the extracted_data before confirming.
    """
    from orchestrator.project_graph import persistence_app

    initial_state = {
        "query": f"Confirm project: {req.project_name}",
        "response": "",
        "next_node": "",
        "agent_outputs": [],
        "debug_log": "",
        "project_name": req.project_name,
        "project_code": req.project_code,
        "opportunity_id": req.opportunity_id,
        "uploaded_files": [],
        "extracted_data": req.extracted_data,
        "user_confirmed": True,
        "operation_mode": "create_project",
        "collection_names": [],
    }

    try:
        result = persistence_app.invoke(initial_state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")

    return {
        "status": "created" if "✅" in result.get("response", "") else "error",
        "response": result.get("response", ""),
        "debug_log": result.get("debug_log", ""),
    }


@server.get("/dashboard")
def dashboard():
    """Portfolio MBR dashboard — returns markdown report + per-project JSON for UI rendering."""
    from agents.mbr_agent import mbr_agent_node, _fetch_portfolio, _compute_financials, _fetch_open_raids
    result = mbr_agent_node({
        "query": "portfolio dashboard",
        "debug_log": "",
        "agent_outputs": [],
        "history": [],
        "response": "",
        "next_node": "",
    })

    # Also return structured JSON for the dashboard UI
    projects = _fetch_portfolio()
    structured = []
    for p in projects:
        f = _compute_financials(p)
        raids = _fetch_open_raids(p["project_id"])
        structured.append({
            "project_id":     p["project_id"],
            "project_number": p["ProjectNumber"],
            "customer":       p["customer"],
            "pm":             p["PMName"],
            "country":        p["country"],
            "stage":          p["Proj_Stage"] or "—",
            "start_date":     p["startdateContract"],
            "end_date":       p["endDateContract"],
            "financials":     f,
            "raids": {
                "total": p["total_raids"],
                "open":  p["raids_open"],
                "high":  p["raids_high"],
                "medium":p["raids_medium"],
                "low":   p["raids_low"],
            },
            "open_raid_items": raids,
        })

    return {
        "report":   result["response"],
        "projects": structured,
        "debug_log": result.get("debug_log", ""),
    }


@server.get("/raid/alerts")
def get_raid_alerts():
    """
    Returns ALL open/in-progress RAID items that are past their DueDate.
    Requires local SQLite tracking active.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    db_path = os.getenv("SQLITE_DB_PATH", "./data/openclaw.db")
    db_abs = db_path if os.path.isabs(db_path) else os.path.abspath(os.path.join(project_root, db_path))
    
    if not os.path.exists(db_abs):
        return {"alerts": []}
        
    import sqlite3
    try:
        conn = sqlite3.connect(db_abs)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check DueDate < today. Status NOT IN closed/resolved.
        # Ensure DueDate isn't blank or null.
        cursor.execute("""
            SELECT R.raidID, R.project_id, R.Description, R.owner, R.DueDate, R.Status, P.ProjectNumber, P.customer
            FROM RAIDitems R
            JOIN Project P ON R.project_id = P.project_id
            WHERE R.DueDate != '' 
              AND R.DueDate IS NOT NULL
              AND date(R.DueDate) < date('now')
              AND LOWER(R.Status) NOT IN ('closed', 'resolved')
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        alerts = [dict(r) for r in rows]
        return {"alerts": alerts}
        
    except Exception as e:
        print(f"Error fetching RAID alerts: {e}")
        return {"alerts": []}


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("ORCHESTRATOR_HOST", "localhost")
    port = int(os.getenv("ORCHESTRATOR_PORT", "8000"))
    uvicorn.run("main:server", host=host, port=port, reload=True)
