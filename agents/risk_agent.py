"""
Agent Mesh – Risk Agent
Extracts a project identifier (Project Number or Opportunity ID) from the query.
Checks SQLite for `ProjectWorkPackage` baseline risks and `RAIDitems` live operational risks.
If found, builds a risk analysis from the DB.
If not found, searches `contract_collection` via RAG and uses the risk markdown prompt.
"""
import sys
import os
import sqlite3
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from orchestrator.llm_factory import get_llm
from langchain_core.messages import SystemMessage, HumanMessage
from tools.retrieval import similarity_search

load_dotenv()

llm = get_llm()

# Prompt to extract the ID from the query
EXTRACTION_PROMPT = """You are an AI assistant that extracts project identifiers from text.
The user wants risk analysis or RAID log information.
Extract either the Project Number, Opportunity ID, or SOW ID mentioned in the query.
If multiple are found, return the most obvious one.
Return ONLY the raw identifier string, with no extra text, markdown, or punctuation.
If no clear identifier is found, return exactly: NONE"""

# Risk RAG Prompt requested by user
def _get_risk_prompt() -> str:
    return """
You are an expert contract analyst. Extract and analyze risk-related information from the contract document.

Based on the document text provided, identify and format risk information in a professional Markdown format.

Document Text: {document_text}

Extract risk analysis for SOW ID: {sow_id}

Format your response using the following Markdown structure EXACTLY:

# ⚠️ Contract Risk Analysis

**Document ID:** {sow_id}

## 🎯 Risk Assessment Summary
[Provide an overall risk assessment of the contract in 2-3 sentences]

## 📋 Identified Risks

### 🔴 High Risk Items
| Risk Category | Description | Impact | Probability | Mitigation Strategy |
|---------------|-------------|--------|-------------|-------------------|
| [Category] | [Description] | High | [High/Medium/Low] | [Mitigation approach] |

### 🟡 Medium Risk Items
| Risk Category | Description | Impact | Probability | Mitigation Strategy |
|---------------|-------------|--------|-------------|-------------------|
| [Category] | [Description] | Medium | [High/Medium/Low] | [Mitigation approach] |

### 🟢 Low Risk Items
| Risk Category | Description | Impact | Probability | Mitigation Strategy |
|---------------|-------------|--------|-------------|-------------------|
| [Category] | [Description] | Low | [High/Medium/Low] | [Mitigation approach] |

## 🛡️ Risk Mitigation Recommendations
1. **[Priority 1]:** [Detailed recommendation]
2. **[Priority 2]:** [Detailed recommendation]
3. **[Priority 3]:** [Detailed recommendation]

## 📊 Risk Matrix Summary
- **Total Risks Identified:** [Number]
- **High Priority:** [Number]
- **Medium Priority:** [Number]
- **Low Priority:** [Number]

---
*Risk analysis completed for SOW: {sow_id}*
"""


def _extract_identifier(query: str) -> str:
    try:
        response = llm.invoke([
            SystemMessage(content=EXTRACTION_PROMPT),
            HumanMessage(content=query)
        ])
        result = response.content.strip()
        if result == "NONE" or not result:
            return ""
        return result
    except Exception:
        return ""


def _build_db_markdown(project: dict, wps: list, raids: list, identifier: str) -> str:
    """Builds the requested markdown format using data from SQLite tables."""
    
    project_number = project.get("ProjectNumber", identifier)
    # Basic metrics
    baseline_risk_count = len(wps)
    live_risk_count = sum(1 for r in raids if str(r.get("Type", "")).lower() == "risk")
    issue_count = sum(1 for r in raids if str(r.get("Type", "")).lower() == "issue")
    
    total_items = baseline_risk_count + len(raids)
    
    high_count = sum(1 for r in raids if str(r.get("Status", "")).lower() in ["open", "critical", "high"])
    med_count = sum(1 for r in raids if str(r.get("Status", "")).lower() in ["medium", "in-progress"])
    low_count = sum(1 for r in raids if str(r.get("Status", "")).lower() in ["low", "closed", "resolved"])

    md = f"# ⚠️ Contract Risk Analysis\n\n"
    md += f"**Document ID:** `{project_number}`\n\n"
    
    md += f"## 🎯 Risk Assessment Summary\n"
    if total_items == 0:
        md += "No baseline risks or operational RAID items have been formally recorded for this project yet.\n\n"
    else:
        md += f"This project currently tracks **{live_risk_count} live risks** and **{issue_count} live issues** in its operational RAID log. "
        md += f"Additionally, there are **{baseline_risk_count} baseline risks** established across the work packages identified in the SOW.\n\n"

    md += f"## 📋 Identified Risks\n\n"

    # Separate RAID items into basic buckets based on status/type heuristic
    high_raids = [r for r in raids if str(r.get("Status", "")).lower() in ["open", "critical", "high"]]
    med_raids = [r for r in raids if str(r.get("Status", "")).lower() not in ["open", "critical", "high", "closed", "resolved", "low"]]
    low_raids = [r for r in raids if str(r.get("Status", "")).lower() in ["closed", "resolved", "low"]]

    # HELPER for displaying table rows
    def _raid_table(raid_list, impact_label):
        if not raid_list:
            return f"| None | No {impact_label} items recorded | {impact_label} | N/A | N/A | N/A | N/A |\n"
        tbl = ""
        for r in raid_list:
            cat = r.get("Category") or r.get("Type") or "General"
            desc = (r.get("Description") or "").replace("\n", " ").strip()
            owner = r.get("owner", "Unassigned")
            due_date = r.get("DueDate", "No Date")
            mit_action = r.get("MitigatingAction") or r.get("ROAM") or "No mitigation stated"
            
            # Format row
            tbl += f"| {cat} | {desc} | {impact_label} | {owner} | {due_date} | {r.get('Status','Unknown')} | {mit_action} |\n"
        return tbl
        
    md += f"### 🔴 High Risk & Operational Items\n"
    md += f"| Type/Category | Description | Impact | Owner | Due Date | Status | Mitigating Actions (ROAM) |\n"
    md += f"|---------------|-------------|--------|-------|----------|--------|----------------------------|\n"
    md += _raid_table(high_raids, "High")
    md += "\n"
    
    md += f"### 🟡 Medium Risk & Operational Items\n"
    md += f"| Type/Category | Description | Impact | Owner | Due Date | Status | Mitigating Actions (ROAM) |\n"
    md += f"|---------------|-------------|--------|-------|----------|--------|----------------------------|\n"
    md += _raid_table(med_raids, "Medium")
    md += "\n"
    
    md += f"### 🟢 Low / Closed Items\n"
    md += f"| Type/Category | Description | Impact | Owner | Due Date | Status | Mitigating Actions (ROAM) |\n"
    md += f"|---------------|-------------|--------|-------|----------|--------|----------------------------|\n"
    md += _raid_table(low_raids, "Low")
    md += "\n"

    md += f"## 🛡️ Baseline SOW Work Package Risks\n"
    if wps:
        for idx, wp in enumerate(wps):
            phase = wp.get("phase_name", f"Phase {idx+1}")
            r_and_m = wp.get("risks_mitigations", "None documented")
            md += f"{idx+1}. **[{phase}]**: {r_and_m}\n"
    else:
        md += "- No specific work package baseline risks found.\n"
    md += "\n"

    md += f"## 📊 Risk Matrix Summary\n"
    md += f"- **Total LIVE RAID Items Recorded:** {len(raids)}\n"
    md += f"- **High Priority (Open/Critical):** {high_count}\n"
    md += f"- **Medium Priority (In Progress):** {med_count}\n"
    md += f"- **Low / Resolved Priority:** {low_count}\n"
    md += f"- **SOW Baseline Risk Checkpoints:** {baseline_risk_count}\n\n"

    md += f"---\n*Risk analysis completed for project: {project_number} (via SQLite Database)*\n"
    
    return md


def risk_agent_node(state: dict) -> dict:
    query = state.get("query", "")
    debug = state.get("debug_log", "")
    
    # 1. Extract identifier
    identifier = _extract_identifier(query)
    
    if not identifier:
        debug += "\n⚠️ Risk Agent: Could not find a clear Project or SOW ID in request. Falling back to semantic search."
        identifier = "Unknown Document"
    else:
        debug += f"\n🔍 Risk Agent: Extracted target ID '{identifier}'"
        
        # 2. Database connection check
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        env_val = os.getenv("SQLITE_DB_PATH", "./data/openclaw.db")
        db_path = env_val if os.path.isabs(env_val) else os.path.abspath(os.path.join(project_root, env_val))
        
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Fetch Project
                cursor.execute("SELECT * FROM Project WHERE ProjectNumber = ? OR OpportunityID = ?", (identifier, identifier))
                proj_row = cursor.fetchone()
                
                if proj_row:
                    proj_id = proj_row["project_id"]
                    
                    # Fetch WorkPackages (Baseline risks)
                    cursor.execute("SELECT phase_name, risks_mitigations FROM ProjectWorkPackage WHERE project_id = ?", (proj_id,))
                    wp_rows = [dict(r) for r in cursor.fetchall()]
                    
                    # Fetch RAIDitems (Operational risks)
                    # Suppressing errors if RAIDitems table doesn't exist yet in heavily modified testing sets
                    raid_rows = []
                    try:
                        cursor.execute("SELECT * FROM RAIDitems WHERE project_id = ?", (proj_id,))
                        raid_rows = [dict(r) for r in cursor.fetchall()]
                    except sqlite3.OperationalError:
                        debug += "\n⚠️ Risk Agent: RAIDitems table not found. Skipping live risks."
                    
                    conn.close()
                    
                    debug += f"\n✅ Risk Agent: Project found in SQLite database. Compiling structured risk report."
                    md_text = _build_db_markdown(dict(proj_row), wp_rows, raid_rows, identifier)
                    return {
                        "response": md_text,
                        "debug_log": debug
                    }
                else:
                    conn.close()
            except Exception as exc:
                debug += f"\n⚠️ Risk Agent DB error: {exc}"
    
    # 3. Fallback to RAG if not found in DB
    debug += f"\n⚠️ Risk Agent: '{identifier}' not found in SQLite. Falling back to Vector DB (contract_collection) RAG search."
    
    try:
        context_str = similarity_search("contract_collection", query, k=4)

        if not context_str:
            debug += "\n❌ Risk Agent: No relevant context found in ChromaDB either."
            return {
                "response": f"I couldn't find risk analysis information for {identifier} in the database or the uploaded contracts. Please ensure the project is created or the SOW is uploaded.",
                "debug_log": debug
            }
        
        rag_prompt = _get_risk_prompt().format(
            document_text=context_str,
            sow_id=identifier
        )
        
        response = llm.invoke([HumanMessage(content=rag_prompt)])
        final_answer = response.content.strip()
        
        # Append suggestion to create project
        suggestion = "\n\n> 💡 **Tip:** This baseline risk analysis was retrieved using semantic search from contract text. For robust live operational risk tracking, please use the **Create Project** flow and track via the RAID log!"
        final_answer += suggestion
        
        return {
            "response": final_answer,
            "debug_log": debug
        }
        
    except Exception as exc:
        debug += f"\n❌ Risk Agent RAG error: {exc}"
        return {
            "response": f"❌ An error occurred while retrieving risk analysis: {exc}",
            "debug_log": debug
        }
