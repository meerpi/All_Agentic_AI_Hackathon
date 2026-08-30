"""
End-to-End Verification Test for Autonomous Freelance Pipeline Coordinator.
"""

import sys
import logging
from agent.inbox_watcher import watcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test.pipeline")

def test_pipeline():
    sample_inquiry = {
        "sender": "Sarah Jenkins <sarah.jenkins@lumina-health.io>",
        "subject": "Inquiry: NextGen Patient Portal & Analytics Dashboard",
        "body": (
            "Hi Anima,\n\n"
            "We came across your recent work and are looking for a lead full-stack AI engineer "
            "to build our HIPAA-compliant Patient Analytics Dashboard with Gemini-powered medical summaries.\n\n"
            "Project Scope:\n"
            "- React + Tailwind dashboard frontend\n"
            "- FastAPI backend with Firestore database\n"
            "- Gemini 1.5/2.0 multimodal report generation\n"
            "- Target Launch: 6 weeks\n"
            "- Budget: $12,500 USD\n\n"
            "Are you available for a 45-minute discovery call this week to discuss technical feasibility and scope?\n\n"
            "Best regards,\n"
            "Sarah Jenkins\n"
            "VP of Engineering, Lumina Health"
        ),
        "source": "SIMULATED_TEST"
    }

    print("🚀 Triggering Autonomous Pipeline Coordinator for simulated client inquiry...")
    print(f"From: {sample_inquiry['sender']}")
    print(f"Subject: {sample_inquiry['subject']}\n")

    plan = watcher.process_inquiry(
        sender=sample_inquiry["sender"],
        subject=sample_inquiry["subject"],
        body=sample_inquiry["body"],
        source="TEST_SUITE"
    )

    print("\n==========================================")
    print(f"Workflow ID: {plan.workflow_id}")
    print(f"Status: {plan.status.value}")
    print(f"Total Steps Executed: {len(plan.steps)}")
    print("==========================================")

    for step in plan.steps:
        print(f"\nStep {step.step_number}: [{step.tool_name}] -> {step.status.value}")
        print(f"  Description: {step.description}")
        print(f"  Result: {step.result}")

    print("\n--- Executive Summary ---")
    print(plan.summary)

if __name__ == "__main__":
    test_pipeline()
