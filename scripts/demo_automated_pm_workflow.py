"""
Verification Test for 'Automated Product Manager' Workflow.
Transcripts ➔ Action Items ➔ Jira Tasks ➔ Google Docs Meeting Minutes ➔ Google Sheets ➔ Slack Announcement.
"""

import logging
from agent.models import TaskGoal
from agent.orchestrator import TaskmasterOrchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test.automated_pm")

def test_automated_pm():
    transcript_sample = (
        "Meeting Transcript: Sprint 42 Planning & Architecture Review\n"
        "Attendees: Anima (Lead), Alex Chen (Frontend), Priya Patel (Backend), Marcus Vance (Security), David Kim (Product)\n"
        "Date: August 30, 2026\n\n"
        "David: Okay team, three critical items came out of our customer reviews.\n"
        "First, the frontend auth flow is still using legacy session cookies. We need Alex to migrate the React client to JWT bearer tokens with refresh token rotation. This is High priority for next sprint.\n"
        "Alex: Got it. I'll need about 5 story points for that.\n\n"
        "David: Second, billing API latency spiked to 2.4s under peak load. Priya, we need you to add Redis caching and optimize the BigQuery billing summary queries. Critical priority.\n"
        "Priya: On it. Estimating 8 story points. We should target sub-200ms latency.\n\n"
        "David: Third, Marcus, SOC2/HIPAA auditors requested immutable audit logging for all admin user role changes. Medium priority.\n"
        "Marcus: Easy, I can wire that into our Cloud Audit Logs pipeline. 3 story points.\n\n"
        "David: Great. Anima, please synthesize the minutes, log the Jira tickets, update the sprint sheet, and post the summary to #product-updates."
    )

    goal_text = (
        "Act as an Automated Product Manager.\n"
        "1. Analyze the meeting transcript, extracting attendees, key decisions, and action items with assignees, story points, and priorities.\n"
        "2. Create the corresponding engineering tasks in Jira (project key: PROD).\n"
        "3. Generate a comprehensive Executive Meeting Minutes & Decision Log in Google Docs.\n"
        "4. Append the new action items and Jira keys to the Sprint Backlog Google Sheet.\n"
        "5. Post an executive Slack announcement card to #product-updates linking the Jira tasks and Google Doc.\n"
        "6. Validate that all extracted action items have matching Jira tickets and deliverables."
    )

    print("🚀 Triggering Automated Product Manager Workflow...")
    print(f"Goal: {goal_text[:120]}...\n")

    orchestrator = TaskmasterOrchestrator()
    task_goal = TaskGoal(
        goal=goal_text,
        context={
            "transcript": transcript_sample,
            "meeting_title": "Sprint 42 Planning & Architecture Review",
            "workflow_type": "AUTOMATED_PRODUCT_MANAGER"
        }
    )

    plan = orchestrator.create_plan(task_goal)
    print(f"\n[Generated Plan] ID: {plan.workflow_id} | Total Steps: {len(plan.steps)}")
    for s in plan.steps:
        print(f"  Step {s.step_number}: [{s.tool_name}] -> {s.description}")

    executed_plan = orchestrator.execute_workflow(plan.workflow_id)

    print("\n==========================================")
    print(f"Execution Status: {executed_plan.status.value}")
    print(f"Total Steps Finished: {len(executed_plan.steps)}")
    print("==========================================")

    for step in executed_plan.steps:
        print(f"\nStep {step.step_number}: [{step.tool_name}] -> {step.status.value}")
        print(f"  Description: {step.description}")
        print(f"  Result: {step.result}")

    print("\n--- Executive Summary ---")
    print(executed_plan.summary)

if __name__ == "__main__":
    test_automated_pm()
