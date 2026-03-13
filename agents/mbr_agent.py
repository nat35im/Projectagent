"""
MBR Agent – Monthly Business Review portfolio dashboard.

Queries all projects + RAID items, computes revenue/loss forecasts,
RAID risk counts, and generates LLM recovery plans for AT RISK / DELAYED projects.
"""
import sys, os, sqlite3, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from orchestrator.llm_factory import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

llm = get_llm()

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DB_PATH_ENV = os.getenv("SQLITE_DB_PATH", "./data/openclaw.db")
DB_PATH = _DB_PATH_ENV if os.path.isabs(_DB_PATH_ENV) else os.path.abspath(os.path.join(PROJECT_ROOT, _DB_PATH_ENV))

STATUS_ICONS = {
    "AT RISK":  "🔴",
    "DELAYED":  "🟠",
    "ON TRACK": "🟢",
    "CLOSED":   "⚫",
    "COMPLETE": "✅",
}


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_portfolio() -> list[dict]:
    """Return all projects with aggregated RAID counts."""
    conn = _get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                p.project_id,
                p.ProjectNumber,
                p.customer,
                p.PMName,
                p.country,
                p.Proj_Stage,
                p.startdateContract,
                p.endDateContract,
                p.Baseline_Rev,
                p.Baseline_Cost,
                p.total_project_cost,
                p.ActiveCurrency,
                p.revenue_json,
                p.total_hours_json,
                COUNT(r.raidID)                                         AS total_raids,
                SUM(CASE WHEN LOWER(r.Status) NOT IN ('closed','resolved')
                         AND LOWER(r.Category) = 'high'  THEN 1 ELSE 0 END) AS raids_high,
                SUM(CASE WHEN LOWER(r.Status) NOT IN ('closed','resolved')
                         AND LOWER(r.Category) = 'medium' THEN 1 ELSE 0 END) AS raids_medium,
                SUM(CASE WHEN LOWER(r.Status) NOT IN ('closed','resolved')
                         AND LOWER(r.Category) = 'low'   THEN 1 ELSE 0 END) AS raids_low,
                SUM(CASE WHEN LOWER(r.Status) NOT IN ('closed','resolved') THEN 1 ELSE 0 END) AS raids_open
            FROM Project p
            LEFT JOIN RAIDitems r ON r.project_id = p.project_id
            GROUP BY p.project_id
            ORDER BY p.ProjectNumber
        """)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _fetch_open_raids(project_id: str) -> list[dict]:
    """Return open RAID items for a project."""
    conn = _get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT Type, Category, owner, Description, MitigatingAction, DueDate, Status
            FROM RAIDitems
            WHERE project_id = ?
              AND LOWER(Status) NOT IN ('closed','resolved')
            ORDER BY Category DESC, DueDate ASC
        """, (project_id,))
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _compute_financials(p: dict) -> dict:
    """Compute revenue variance, margin, and forecast figures."""
    baseline_rev  = p.get("Baseline_Rev") or 0
    actual_cost   = p.get("total_project_cost") or 0
    baseline_cost = p.get("Baseline_Cost") or 0
    currency      = p.get("ActiveCurrency") or "SGD"

    rev_variance  = baseline_rev - actual_cost
    margin_pct    = (rev_variance / baseline_rev * 100) if baseline_rev else 0
    cost_overrun  = actual_cost - baseline_cost
    at_loss       = rev_variance < 0

    # Parse revenue_json for actuals if present
    actual_rev = 0
    try:
        rev_data = json.loads(p.get("revenue_json") or "{}")
        actual_rev = rev_data.get("actual_revenue", 0)
    except Exception:
        pass

    return {
        "currency":     currency,
        "baseline_rev": baseline_rev,
        "actual_cost":  actual_cost,
        "rev_variance": rev_variance,
        "margin_pct":   round(margin_pct, 1),
        "cost_overrun": cost_overrun,
        "at_loss":      at_loss,
        "actual_rev":   actual_rev,
    }


def _recovery_plan(project: dict, raids: list[dict], financials: dict) -> str:
    """Ask LLM to produce a concise recovery plan for an at-risk/delayed project."""
    raids_text = "\n".join(
        f"- [{r['Type']}][{r['Category']}] {r['Description']} "
        f"(Owner: {r['owner'] or 'Unassigned'}, Due: {r['DueDate'] or 'N/A'}, "
        f"Mitigation: {r['MitigatingAction'] or 'None'})"
        for r in raids
    ) or "No open RAID items."

    prompt = f"""You are a Senior Project Manager preparing a recovery plan for an executive MBR report.

Project: {project['customer']} (#{project['ProjectNumber']})
Status: {project['Proj_Stage'] or 'Unknown'}
Contract period: {project['startdateContract']} → {project['endDateContract']}
Revenue baseline: {financials['currency']} {financials['baseline_rev']:,.0f}
Actual cost to date: {financials['currency']} {financials['actual_cost']:,.0f}
Variance: {financials['currency']} {financials['rev_variance']:,.0f} ({financials['margin_pct']}% margin)

Open RAID items:
{raids_text}

Write a concise recovery plan (3-5 bullet points) covering:
1. Immediate actions (this week)
2. Short-term remediation (next 2-4 weeks)
3. Escalation recommendations if needed
Be specific and actionable. No filler. Output plain markdown bullets only."""

    try:
        resp = llm.invoke([SystemMessage(content="You are a concise, experienced project delivery manager."),
                           HumanMessage(content=prompt)])
        return resp.content.strip()
    except Exception as exc:
        return f"_(Recovery plan unavailable: {exc})_"


def _build_report(projects: list[dict]) -> str:
    today = __import__("datetime").date.today().strftime("%d %b %Y")
    lines = [
        f"# 📊 OpenClaw Portfolio Dashboard",
        f"**Report Date:** {today}  |  **Projects:** {len(projects)}\n",
        "---\n",
        "## Portfolio Summary\n",
    ]

    # Summary table
    lines.append("| # | Project | Customer | Stage | Baseline Rev | Cost | Variance | Margin | Open Risks |")
    lines.append("|---|---------|----------|-------|-------------|------|----------|--------|------------|")
    for i, p in enumerate(projects, 1):
        f   = _compute_financials(p)
        stg = p.get("Proj_Stage") or "—"
        ico = STATUS_ICONS.get(stg.upper(), "⚪")
        var_str = f"{f['currency']} {f['rev_variance']:+,.0f}"
        lines.append(
            f"| {i} | #{p['ProjectNumber']} | {p['customer']} | {ico} {stg} "
            f"| {f['currency']} {f['baseline_rev']:,.0f} "
            f"| {f['currency']} {f['actual_cost']:,.0f} "
            f"| {var_str} "
            f"| {f['margin_pct']}% "
            f"| 🔴×{p['raids_high']} 🟠×{p['raids_medium']} 🟡×{p['raids_low']} |"
        )
    lines.append("")

    # Per-project detail
    lines.append("---\n## Project Details\n")
    for p in projects:
        f    = _compute_financials(p)
        stg  = p.get("Proj_Stage") or "Unknown"
        ico  = STATUS_ICONS.get(stg.upper(), "⚪")
        raids = _fetch_open_raids(p["project_id"])

        lines.append(f"### {ico} {p['customer']} — Project #{p['ProjectNumber']}")
        lines.append(f"**PM:** {p['PMName'] or 'N/A'}  |  **Country:** {p['country'] or 'N/A'}  |  "
                     f"**Period:** {p['startdateContract']} → {p['endDateContract']}")
        lines.append(f"**Stage:** `{stg}`  |  "
                     f"**Baseline Rev:** {f['currency']} {f['baseline_rev']:,.0f}  |  "
                     f"**Actual Cost:** {f['currency']} {f['actual_cost']:,.0f}  |  "
                     f"**Variance:** {f['currency']} {f['rev_variance']:+,.0f} ({f['margin_pct']}%)\n")

        if raids:
            lines.append(f"**Open RAID Items ({len(raids)}):**")
            lines.append("| Type | Priority | Owner | Status | Due | Description |")
            lines.append("|------|----------|-------|--------|-----|-------------|")
            for r in raids:
                lines.append(
                    f"| {r['Type']} | {r['Category'] or '—'} | {r['owner'] or '—'} "
                    f"| {r['Status']} | {r['DueDate'] or '—'} "
                    f"| {(r['Description'] or '')[:80]} |"
                )
            lines.append("")
        else:
            lines.append("_No open RAID items._\n")

        # Recovery plan for at-risk / delayed projects
        if stg.upper() in ("AT RISK", "DELAYED"):
            lines.append(f"**🛠 Recovery Plan:**")
            plan = _recovery_plan(p, raids, f)
            lines.append(plan)
            lines.append("")

        lines.append("---\n")

    return "\n".join(lines)


def mbr_agent_node(state: dict) -> dict:
    debug = state.get("debug_log", "")
    try:
        projects = _fetch_portfolio()
        if not projects:
            return {
                "response": "No projects found in the database.",
                "debug_log": debug + "\n📊 MBR Agent: no projects found."
            }
        report = _build_report(projects)
        return {
            "response": report,
            "debug_log": debug + f"\n📊 MBR Agent: portfolio report generated ({len(projects)} projects)."
        }
    except Exception as exc:
        return {
            "response": f"❌ MBR Agent error: {exc}",
            "debug_log": debug + f"\n❌ MBR Agent exception: {exc}"
        }
