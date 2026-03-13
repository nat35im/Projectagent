#!/usr/bin/env python
"""
Daily portfolio report script — called by cron at 8am.
Generates the MBR dashboard report and prints it to stdout.
Email sending is KIV — add tools/email_report.py integration here when ready.

Usage:
  cd /Users/nathaniel.sim/ClaudeProjects/Projectagent
  python tools/daily_report.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

import datetime

def main():
    print(f"\n{'='*60}")
    print(f"  OpenClaw Daily Portfolio Report")
    print(f"  {datetime.datetime.now().strftime('%d %b %Y %H:%M')}")
    print(f"{'='*60}\n")

    from agents.mbr_agent import mbr_agent_node
    result = mbr_agent_node({
        "query": "daily portfolio dashboard",
        "debug_log": "",
        "agent_outputs": [],
        "history": [],
        "response": "",
        "next_node": "",
    })

    report = result.get("response", "")
    if not report or report.startswith("❌"):
        print(f"ERROR: {report}")
        sys.exit(1)

    print(report)
    print(f"\n{'='*60}")
    print("  Report complete.")
    print(f"{'='*60}\n")

    # TODO: Send via email when ready
    # from tools.email_report import send_report
    # send_report(subject=f"OpenClaw MBR Report – {datetime.date.today()}", body_markdown=report)


if __name__ == "__main__":
    main()
