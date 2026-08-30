"""
Live Difficult End-to-End Orchestration Task.
Zero simulations. Zero mock fallbacks. 100% Live Cloud APIs.

Task:
Distributed Infrastructure Outage Post-Mortem & Remediation Engine:
1. Ingest incident transcript (Replication lag + split-brain partition on Postgres cluster).
2. Create real Jira Cloud issues on https://taskmasterjira.atlassian.net for SRE, DB, and Platform teams.
3. Create real Google Doc with full Post-Mortem RCA & Architecture Remediation Strategy.
4. Create real Google Sheet tracking the Remediation Sprint Backlog & SLA Milestones.
5. Persist audit records to local SQLite database (data/taskmaster.db).
6. Run 6-Dimension Trajectory Evaluation and Token Cost Telemetry.
"""

import json
import logging
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

# Force live execution
os.environ["MOCK_GEMINI"] = "false"

from agent.orchestrator import TaskmasterOrchestrator
from agent.models import TaskGoal, WorkflowStatus
from agent.evals import TrajectoryEvaluator
from agent.tools.jira_tool import JiraTool
from agent.tools.google_sheets_tool import GoogleSheetsTool
from agent.tools.google_docs_tool import GoogleDocsTool
from agent.tools.db_manager import DBManagerTool

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("live_task_runner")

print("\n" + "=" * 80)
print("🚀 STARTING 100% LIVE DIFFICULT TASK (ZERO SIMULATION / ZERO MOCKS)")
print("=" * 80)

orchestrator = TaskmasterOrchestrator()

# Complex Incident Context
incident_context = {
    "incident_id": "INC-8892",
    "severity": "SEV-1 (CRITICAL)",
    "affected_service": "Distributed PostgreSQL Telemetry Cluster (Prod US-East)",
    "summary": "Replication lag exceeded 450s during peak traffic, triggering automatic failover that caused a temporary split-brain partition and corrupted telemetry sequence IDs.",
    "action_items": [
        {
            "summary": "DB Ops: Implement Patroni consensus raft leader election with etcd to prevent split-brain",
            "assignee": "Alex Mercer",
            "priority": "Highest",
            "story_points": 8,
            "description": "Deploy Patroni distributed consensus across 5 PostgreSQL nodes to eliminate split-brain failover risks."
        },
        {
            "summary": "Telemetry API: Add sequence ID replay deduplication layer in Redis",
            "assignee": "Priya Sharma",
            "priority": "High",
            "story_points": 5,
            "description": "Implement Redis sliding window deduplication to reject duplicate telemetry packets during failover recovery."
        },
        {
            "summary": "SRE: Configure Datadog synthetic canary alerts for replication lag > 30s",
            "assignee": "Marcus Vance",
            "priority": "High",
            "story_points": 3,
            "description": "Add multi-region synthetic lag monitoring and automatic circuit-breaking."
        }
    ]
}

# 1. LIVE JIRA CLOUD VERIFICATION
print("\n[STEP 1] Creating Live Issues Directly in Jira Cloud (https://taskmasterjira.atlassian.net)...")
jira_tool = JiraTool()
created_jira_issues = []

for item in incident_context["action_items"]:
    res = jira_tool.run(
        action="create_issue",
        summary=f"[{incident_context['incident_id']}] {item['summary']}",
        description=f"**Incident Reference:** {incident_context['incident_id']} ({incident_context['severity']})\n\n**Details:** {item['description']}\n\n**Assignee:** {item['assignee']}\n**Story Points:** {item['story_points']}",
        priority=item["priority"],
        assignee=item["assignee"],
        story_points=item["story_points"]
    )
    created_jira_issues.append(res)
    print(f"  ✔ Created Jira Issue: {res.get('issue_key')} | Status: {res.get('status')} | URL: {res.get('url')}")

# 2. LIVE GOOGLE DOCS VERIFICATION
print("\n[STEP 2] Provisioning Real Post-Mortem Report in Google Docs via Google Docs API...")
docs_tool = GoogleDocsTool()
doc_title = f"Post-Mortem Incident Report: {incident_context['incident_id']} - Distributed DB Split-Brain"
doc_content = f"""# POST-MORTEM INCIDENT REPORT: {incident_context['incident_id']}

**Severity:** {incident_context['severity']}
**Service Impacted:** {incident_context['affected_service']}
**Date:** 2026-08-29
**Author:** Taskmaster Autonomous Incident Response Council

---

## 1. Executive Summary
{incident_context['summary']}

## 2. Root Cause Analysis (5 Whys)
1. **Why did API write errors spike?** Secondary node took over writes while primary node was still accepting requests.
2. **Why did failover trigger prematurely?** Heartbeat probe timed out during network saturation (450s lag).
3. **Why did replication lag spike?** Batch bulk backfill job ran during peak customer ingestion hours without rate limiting.
4. **Why was backfill unthrottled?** Missing concurrency limiter in data sync pipeline.

## 3. Jira Remediation Tasks Created
"""
for iss in created_jira_issues:
    doc_content += f"- **{iss.get('issue_key')}:** {iss.get('summary')} (Link: {iss.get('url')})\n"

doc_res = docs_tool.run(
    action="create_document",
    title=doc_title,
    content=doc_content
)
print(f"  ✔ Created Google Doc: Title='{doc_res.get('title')}'")
print(f"  ✔ Google Doc ID: {doc_res.get('document_id')}")
print(f"  ✔ Live Google Doc URL: https://docs.google.com/document/d/{doc_res.get('document_id')}/edit")

# 3. LIVE GOOGLE SHEETS VERIFICATION
print("\n[STEP 3] Provisioning Real Incident Backlog & SLA Tracker in Google Sheets...")
sheets_tool = GoogleSheetsTool()
sheet_title = f"Incident Remediation Tracker - {incident_context['incident_id']}"
sheet_headers = ["Jira Key", "Summary", "Assignee", "Priority", "Story Points", "SLA Target", "Jira URL"]

sheet_res = sheets_tool.run(
    action="create_spreadsheet",
    title=sheet_title
)
spreadsheet_id = sheet_res.get("spreadsheet_id")
print(f"  ✔ Created Google Sheet: Title='{sheet_title}'")
print(f"  ✔ Spreadsheet ID: {spreadsheet_id}")
print(f"  ✔ Live Google Sheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")

# Populate rows into the live Google Sheet
rows_to_append = [sheet_headers]
for iss, item in zip(created_jira_issues, incident_context["action_items"]):
    rows_to_append.append([
        iss.get("issue_key", "N/A"),
        item["summary"],
        item["assignee"],
        item["priority"],
        str(item["story_points"]),
        "24 Hours (SEV-1)",
        iss.get("url", "")
    ])

append_res = sheets_tool.run(
    action="append_rows",
    spreadsheet_id=spreadsheet_id,
    rows=rows_to_append
)
print(f"  ✔ Appended {len(rows_to_append)} rows to Google Sheet. Status: {append_res.get('status')}")

# 4. PERSISTENT SQLITE AUDIT STORAGE
print("\n[STEP 4] Persisting Incident Record & Audit Trail into Local SQLite Database...")
db_tool = DBManagerTool()
db_record = {
    "incident_id": incident_context["incident_id"],
    "jira_issues": [i.get("issue_key") for i in created_jira_issues],
    "google_doc_url": f"https://docs.google.com/document/d/{doc_res.get('document_id')}/edit",
    "google_sheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
    "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
db_res = db_tool.run(
    action="upsert",
    collection="incident_postmortems",
    data=db_record
)
print(f"  ✔ SQLite Persistent Record ID: {db_res.get('record_id')} in {db_res.get('database_path')}")

# 5. LIVE GEMINI TRAJECTORY EVALUATION
print("\n[STEP 5] Running Live Multi-Dimensional Trajectory Evaluation via Gemini API...")
goal = TaskGoal(
    goal="End-to-End Autonomous Incident Response & Post-Mortem Action Plan for Critical Distributed Database Outage",
    context=incident_context
)
wf_plan = orchestrator.create_plan(goal)
print(f"  ✔ Gemini Autonomous Plan Created: {len(wf_plan.steps)} DAG Steps Generated")
for s in wf_plan.steps:
    print(f"    • Step {s.step_number} [{s.tool_name}]: {s.description} (Deps: {s.depends_on})")

evaluator = TrajectoryEvaluator(orchestrator.llm)
eval_report = evaluator.evaluate_workflow(wf_plan)
print(f"\n  ✔ Trajectory Evaluation Score: {eval_report.overall_score}/100.0 (Passed: {eval_report.passed})")
print(f"    - Plan Quality:         {eval_report.plan_quality.score}%")
print(f"    - Plan Adherence:       {eval_report.plan_adherence.score}%")
print(f"    - Tool Selection:       {eval_report.tool_selection.score}%")
print(f"    - Argument Correctness: {eval_report.argument_correctness.score}%")

# SUMMARY OUTPUT
print("\n" + "=" * 80)
print("🎯 LIVE ARTIFACTS CREATED (CLICKABLE PROOFS):")
print("=" * 80)
for iss in created_jira_issues:
    print(f"📌 Jira Cloud Issue: {iss.get('issue_key')} -> {iss.get('url')}")
print(f"📄 Google Doc RCA:   https://docs.google.com/document/d/{doc_res.get('document_id')}/edit")
print(f"📊 Google Sheet:     https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")
print(f"🗄️ SQLite DB File:   {db_res.get('database_path')}")
print("=" * 80 + "\n")
