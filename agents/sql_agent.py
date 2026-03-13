"""
Agent Mesh – Text-to-SQL Dynamic Agent
First responder for all user queries. Infers intent against the SQLite schema.
Generates read-only SELECT queries. If the query cannot be answered by the DB,
it falls back to the RAG specialist router.
"""
import sys
import os
import sqlite3
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orchestrator.state import AgentState
from orchestrator.llm_factory import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

llm = get_llm()

AGENT_NAME = "SQL Inference Agent"

# The precise schema layer representation of our database
SCHEMA_LAYER = """
Table: Project
Columns:
- project_id (TEXT, Primary Key)
- ProjectNumber (TEXT, e.g., 'P-123')
- OpportunityID (TEXT)
- customer (TEXT)
- end_customer (TEXT)
- PMName (TEXT)
- DMName (TEXT)
- country (TEXT)
- startdateContract (TEXT)
- endDateContract (TEXT)
- startdateBaseline (TEXT)
- endDateBaseline (TEXT)
- exchangerate (TEXT)
- MBRReporting_currency (TEXT)
- Proj_Stage (TEXT)
- Prod_Grp (TEXT)
- Portfolio (TEXT)
- Contr_Type (TEXT)
- Rev_Type (TEXT)
- Region (TEXT)
- CMT (TEXT)
- Country_Group (TEXT)
- Project_Owner (TEXT)
- Delivery_Manager (TEXT)
- Q2C_Ops (TEXT)
- Start_Dt (TEXT)
- End_Date (TEXT)
- ActiveCurrency (TEXT)
- Baseline_Rev (INTEGER)
- Baseline_Cost (INTEGER)
- SEGM_percent (FLOAT)
- DEGM_percent (FLOAT)
- EGM_variance_percent (FLOAT)
- total_project_cost (FLOAT)
- travel_cost (FLOAT)
- other_cost (FLOAT)
- sow_json (TEXT)
- resources_json (TEXT)
- invoice_json (TEXT)
- revenue_json (TEXT)
- total_hours_json (TEXT)

Table: ProjectWorkPackage
Columns:
- wp_id (TEXT, Primary Key)
- project_id (TEXT, Foreign Key to Project)
- phase_name (TEXT)
- phase_order (INTEGER)
- prerequisites (TEXT)
- activities (TEXT)
- customer_responsibilities (TEXT)
- out_of_scope (TEXT)
- risks_mitigations (TEXT)
- deliverables (TEXT)
- acceptance_criteria (TEXT)
- overview (TEXT)
- engagement_summary (TEXT)
- scope (TEXT)
- tech_landscape (TEXT)
- key_deliverables (TEXT)
- missing_items (TEXT)
- next_steps (TEXT)
- quick_summary (TEXT)

Table: RAIDitems
Columns:
- raidID (TEXT, Primary Key)
- project_id (TEXT, Foreign Key to Project)
- LastupdateDate (TEXT, UTC)
- Type (TEXT, e.g., Risk, Action, Issue, Decision)
- Category (TEXT, e.g., High/Medium/Low or topic)
- owner (TEXT)
- Description (TEXT)
- MitigatingAction (TEXT)
- DueDate (TEXT)
- ROAM (TEXT, Resolved/Owned/Accepted/Mitigated)
- StartDate (TEXT)
- EndDate (TEXT)
- Status (TEXT, Open/WIP/Closed/Resolved)
- Statusdate (TEXT)
- Status_summary (TEXT)
"""

SQL_GENERATION_PROMPT = f"""
You are an expert SQLite Database Administrator and Data Analyst.
You have access to the following SQLite database schema:

{SCHEMA_LAYER}

Your task is to determine if the user's question can be answered strictly by querying this database.

CRITICAL RULES:
1. If the question CAN be answered (e.g. searching by ID, counting risks, finding project dates), generate ONLY a valid, read-only standard SQLite SELECT statement. 
2. STRING COMPARISON: Always use `LIKE '%term%'` instead of `=` for customer names, project descriptions, or any text fields.
3. FLEXIBILITY: If the user provides multiple identifiers (e.g. a Name AND an ID), use `OR` between them or prioritize the ID to ensure a result is found even if one part is slightly off. 
   Example: `WHERE ProjectNumber LIKE '%202021%' OR customer LIKE '%Boston%'`
4. If the user asks a question about general concepts, methodologies, unstructured contract terms, or something clearly not in the schema, you MUST reply with exactly the word: FALLBACK
5. DO NOT output any markdown blocks (like ```sql), do not explain the query. Output either the raw SQL string starting with SELECT, or the word FALLBACK.
6. Your queries should be safe and read-only. Do not use INSERT/UPDATE/DELETE/DROP.
"""

SYNTHESIS_PROMPT = """
You are a helpful Project Intelligence Analyst.
You have just run a database query to answer the user's question.

User Question: {query}
SQL Executed: {sql}
Database Results (JSON): 
{results}

Write a natural language, professional response answering their question based ONLY on the database results provided. 
Use markdown tables or bullet points if appropriate for readability.
"""

def sql_agent_node(state: AgentState) -> dict:
    query = state["query"]
    current_outputs = state.get("agent_outputs", [])
    debug = state.get("debug_log", "")
    
    # 1. Ask LLM to generate SQL or FALLBACK
    history = state.get("history", [])
    messages = [SystemMessage(content=SQL_GENERATION_PROMPT)]
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=f"PAST USER QUERY: {msg['content']}"))
        else:
            messages.append(HumanMessage(content="PAST RESPONSE: (Data was provided)"))
    
    messages.append(HumanMessage(content=f"CURRENT USER QUERY: {query}"))

    try:
        sql_response = llm.invoke(messages)
        generated_sql = sql_response.content.strip()
        
        # Strip markdown fences if LLM accidentally adds them
        if generated_sql.startswith("```"):
            generated_sql = generated_sql.split('\n', 1)[-1]
        if generated_sql.endswith("```"):
            generated_sql = generated_sql.rsplit('\n', 1)[0]
        generated_sql = generated_sql.strip()
        
    except Exception as e:
        debug += f"\n⚠️ {AGENT_NAME}: LLM SQL generation failed: {e}. Defaulting to FALLBACK."
        generated_sql = "FALLBACK"

    if generated_sql == "FALLBACK" or not generated_sql.upper().startswith("SELECT"):
        return {
            "next_node": "router", # Route to the existing RAG AI Router
            "debug_log": debug + f"\n🔄 {AGENT_NAME}: Question cannot be answered purely via DB. Triggering RAG fallback.",
        }

    debug += f"\n🔍 {AGENT_NAME} generated SQL:\n{generated_sql}"

    # 2. Execute SQL
    results = []
    try:
        db_path = os.getenv("SQLITE_DB_PATH", "./data/openclaw.db")
        if not os.path.isabs(db_path):
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            db_path = os.path.abspath(os.path.join(project_root, db_path))
            
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(generated_sql)
        rows = cursor.fetchall()
        for r in rows:
            results.append(dict(r))
            
        conn.close()
    except Exception as e:
        debug += f"\n❌ {AGENT_NAME}: SQL Execution failed: {e}. Falling back."
        return {
            "next_node": "router",
            "debug_log": debug,
        }

    # 3. Handle Empty Results (Trigger Fallback)
    if not results:
        debug += f"\n⚠️ {AGENT_NAME}: SQL returned 0 results for '{generated_sql}'. Triggering RAG fallback."
        return {
            "next_node": "router",
            "debug_log": debug,
        }

    # 4. Synthesize Results
    formatted_results = json.dumps(results, indent=2)
    final_prompt = SYNTHESIS_PROMPT.format(query=query, sql=generated_sql, results=formatted_results)
    
    try:
        messages = [HumanMessage(content=final_prompt)]
        final_response = llm.invoke(messages)
        report = final_response.content.strip()
    except Exception as e:
        report = f"Failed to synthesize SQL results: {e}"

    full_report = f"--- 🗄️ {AGENT_NAME} Report ---\n{report}\n\n*(Query executed against intelligent database schema)*\n"

    return {
        "response": report,
        "agent_outputs": current_outputs + [full_report],
        "debug_log": debug + f"\n✅ {AGENT_NAME}: Successfully answered directly from SQLite schema inference.",
        "next_node": "END" # Answered! Skip the RAG router.
    }
