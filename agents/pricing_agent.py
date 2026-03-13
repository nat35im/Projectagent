"""
Agent Mesh – Pricing Agent
Extracts a project identifier (Project Number or Opportunity ID) from the query,
first checks the SQLite Project table. If found, builds a pricing summary from DB.
If not found, searches `contract_collection` via RAG and uses the specific markdown prompt.
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
The user wants pricing or payment schedule information.
Extract either the Project Number, Opportunity ID, or SOW ID mentioned in the query.
If multiple are found, return the most obvious one.
Return ONLY the raw identifier string, with no extra text, markdown, or punctuation.
If no clear identifier is found, return exactly: NONE"""

# The exact prompt structure requested by the user
def _get_pricing_prompt() -> str:
    return """
You are an expert contract analyzer. Extract pricing and payment schedule information from the contract document.

Based on the document text provided, format the pricing information in a clear, professional Markdown format.

Document Text: {document_text}

Extract pricing summary and payment schedule for SOW ID: {sow_id}

Format your response using the following Markdown structure EXACTLY:

# 💰 Contract Pricing Analysis

**Document ID:** {sow_id}

## 🏢 Contract Parties
- **Provider:** [Company Name]
- **Customer:** [Company Name]

## 💵 Pricing Summary & Payment Schedule

| Phase | Description | Percentage | Amount (SGD) | Indicative Date |
|-------|-------------|------------|--------------|-----------------|
| Phase 1 | [Description] | XX% | S$XX,XXX.XX | [Date] |
| Phase 2 | [Description] | XX% | S$XX,XXX.XX | [Date] |

### 📊 Financial Summary
- **Subtotal:** S$XXX,XXX.XX
- **Total Contract Value:** S$XXX,XXX.XX
- **Currency:** Singapore Dollars (SGD)

### 📝 Pricing Notes
[Any important pricing notes, exclusions, or terms]

## 📅 Engagement Schedule
- **Start Date:** [DD Month YYYY]
- **End Date:** [DD Month YYYY]
- **Duration:** [X months]

---
*Analysis completed for SOW: {sow_id}*
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


def _build_db_markdown(row: dict, identifier: str) -> str:
    """Builds the requested markdown format using data from the SQLite row."""
    # Row dictionary mapping based on SELECT query
    project_number = row.get("ProjectNumber", identifier)
    opportunity_id = row.get("OpportunityID", "N/A")
    project_owner = row.get("Project_Owner", "Unassigned")
    customer = row.get("customer", "Unknown Customer")
    
    start_date = row.get("startdateContract", "[DD Month YYYY]")
    end_date = row.get("endDateContract", "[DD Month YYYY]")
    
    currency = row.get("MBRReporting_currency", "SGD")
    
    # Financial fields
    total_project_cost = row.get("total_project_cost", 0.0) or 0.0
    baseline_rev = row.get("Baseline_Rev", 0.0) or 0.0
    
    sow_json_str = row.get("sow_json", "{}")
    invoice_json_str = row.get("invoice_json", "[]")
    resources_json_str = row.get("resources_json", "{}")
    revenue_json_str = row.get("revenue_json", "{}")
    
    # 1. Parse JSON fields
    try:
        sow_data = json.loads(sow_json_str) if sow_json_str else {}
        provider = sow_data.get("parties", {}).get("provider", "IntellMetriq Software Pte. Ltd.")
    except Exception:
        sow_data = {}
        provider = "IntellMetriq Software Pte. Ltd."
        
    try:
        invoice_data = json.loads(invoice_json_str) if invoice_json_str else []
    except Exception:
        invoice_data = []
        
    try:
        resources_data = json.loads(resources_json_str) if resources_json_str else {}
        # Try to extract sub-costs if properly formatted
        risk_costs = resources_data.get("other_costs", {}).get("total", 0.0)
        # Assuming resources_json holds base resource cost, or we derive it
        base_resource_cost = resources_data.get("resources", {}).get("total_cost", 0.0)
    except Exception:
        risk_costs = 0.0
        base_resource_cost = 0.0
        
    # Calculate duration
    duration_str = "[X months]"
    try:
        from datetime import datetime
        if start_date and end_date and start_date != "[DD Month YYYY]":
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            months = (ed.year - sd.year) * 12 + (ed.month - sd.month)
            duration_str = f"{max(1, months)} months"
    except Exception:
        pass

    # Build the markdown
    md = f"# 💰 Contract Pricing Analysis\n\n"
    
    md += f"### 📌 Identity Metadata\n"
    md += f"- **Project Number:** `{project_number}`\n"
    md += f"- **Opportunity ID:** `{opportunity_id}`\n"
    md += f"- **Project Owner:** {project_owner}\n\n"

    md += f"## 🏢 Contract Parties\n"
    md += f"- **Provider:** {provider}\n"
    md += f"- **Customer:** {customer}\n\n"
    
    md += f"## 💵 Invoicing Summary & Payment Schedule\n\n"
    md += f"| Phase | Description | Percentage | Amount ({currency}) | Indicative Date |\n"
    md += f"|-------|-------------|------------|--------|-----------------|\n"
    
    if invoice_data and isinstance(invoice_data, list):
        for idx, inv in enumerate(invoice_data):
            desc = inv.get("detail", f"Phase {idx+1}")
            amt = inv.get("amount", "0.00")
            date = inv.get("date", "[Date]")
            perc = "N/A"
            if baseline_rev and baseline_rev > 0:
                try:
                    perc = f"{(float(amt) / float(baseline_rev) * 100):.1f}%"
                except Exception:
                    pass
            md += f"| Phase {idx+1} | {desc} | {perc} | {amt} | {date} |\n"
    else:
        md += f"| Phase 1 | [Description] | XX% | XX,XXX.XX | [Date] |\n"
        
    md += f"\n### 📊 Comprehensive Financial Summary\n"
    
    # Check if we have detailed cost breakdown
    if total_project_cost > 0 or risk_costs > 0 or base_resource_cost > 0:
        md += f"- **Total Revenue:** {currency} {baseline_rev:,.2f}\n"
        md += f"- **Resource Costs:** {currency} {base_resource_cost:,.2f}\n"
        md += f"- **Risk/Other Costs:** {currency} {risk_costs:,.2f}\n"
        md += f"- **Total Project Cost:** {currency} {total_project_cost:,.2f}\n"
        
        try:
            margin = baseline_rev - total_project_cost
            margin_perc = (margin / baseline_rev * 100) if baseline_rev > 0 else 0
            md += f"- **Project Margin:** {currency} {margin:,.2f} ({margin_perc:.1f}%)\n"
        except Exception:
            pass
    else:
        md += f"- **Subtotal:** {currency} {baseline_rev}\n"
        md += f"- **Total Contract Value:** {currency} {baseline_rev}\n"

    md += f"\n### 📝 Pricing Notes\n"
    md += f"Extracted directly from the structured OpenClaw project database.\n\n"
    
    md += f"## 📅 Engagement Schedule\n"
    md += f"- **Start Date:** {start_date}\n"
    md += f"- **End Date:** {end_date}\n"
    md += f"- **Duration:** {duration_str}\n\n"
    
    md += f"---\n*Analysis completed for {identifier} (via Database)*\n"
    
    return md


def pricing_agent_node(state: dict) -> dict:
    query = state.get("query", "")
    debug = state.get("debug_log", "")
    
    # 1. Extract identifier
    identifier = _extract_identifier(query)
    
    if not identifier:
        debug += "\n⚠️ Pricing Agent: Could not find a clear Project or SOW ID in request. Falling back to semantic search."
        identifier = "Unknown Document"
    else:
        debug += f"\n🔍 Pricing Agent: Extracted target ID '{identifier}'"
        
        # 2. Database connection check
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        env_val = os.getenv("SQLITE_DB_PATH", "./data/openclaw.db")
        db_path = env_val if os.path.isabs(env_val) else os.path.abspath(os.path.join(project_root, env_val))
        
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                # Use DictCursor for easier row access
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute(
                    """SELECT ProjectNumber, OpportunityID, Project_Owner, customer, startdateContract, endDateContract, 
                              Baseline_Rev, total_project_cost, MBRReporting_currency, sow_json, invoice_json, resources_json, revenue_json
                       FROM Project 
                       WHERE ProjectNumber = ? OR OpportunityID = ?""",
                    (identifier, identifier)
                )
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    debug += f"\n✅ Pricing Agent: Project found in SQLite database. Compiling structured report."
                    # Convert sqlite3.Row to dict
                    md_text = _build_db_markdown(dict(row), identifier)
                    return {
                        "response": md_text,
                        "debug_log": debug
                    }
            except Exception as exc:
                debug += f"\n⚠️ Pricing Agent DB error: {exc}"
    
    # 3. Fallback to RAG if not found in DB
    debug += f"\n⚠️ Pricing Agent: '{identifier}' not found in SQLite. Falling back to Vector DB (contract_collection) RAG search."
    
    try:
        context_str = similarity_search("contract_collection", query, k=4)

        if not context_str:
            debug += "\n❌ Pricing Agent: No relevant context found in ChromaDB either."
            return {
                "response": f"I couldn't find pricing information for {identifier} in the database or the uploaded contracts. Please ensure the project is created or the SOW is uploaded.",
                "debug_log": debug
            }
        
        rag_prompt = _get_pricing_prompt().format(
            document_text=context_str,
            sow_id=identifier
        )
        
        response = llm.invoke([HumanMessage(content=rag_prompt)])
        final_answer = response.content.strip()
        
        # Append suggestion to create project
        suggestion = "\n\n> 💡 **Tip:** This information was retrieved using semantic search. For faster, structured retrieval, please use the **Create Project** flow for this document!"
        final_answer += suggestion
        
        return {
            "response": final_answer,
            "debug_log": debug
        }
        
    except Exception as exc:
        debug += f"\n❌ Pricing Agent RAG error: {exc}"
        return {
            "response": f"❌ An error occurred while retrieving pricing information: {exc}",
            "debug_log": debug
        }
