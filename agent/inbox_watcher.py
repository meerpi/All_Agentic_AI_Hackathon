"""
Autonomous Inbox & Event Watcher for Freelance Pipeline Coordinator.

Continuously monitors Gmail (or handles webhook events) for incoming client inquiries,
extracts requirements, and triggers the Taskmaster autonomous workflow across
Google Calendar, Docs, Sheets, and Gmail.
"""

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent.models import TaskGoal, WorkflowPlan
from agent.orchestrator import TaskmasterOrchestrator
from agent.tools.gmail_tool import GmailTool

logger = logging.getLogger("taskmaster.watcher")


class InboxWatcher:
    def __init__(self, poll_interval_seconds: int = 30):
        self.poll_interval = poll_interval_seconds
        self.gmail = GmailTool()
        self.orchestrator = TaskmasterOrchestrator()
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._processed_message_ids = set()
        self.events_history: List[Dict[str, Any]] = []

    def start(self):
        """Start the background watcher thread."""
        if self.is_running:
            logger.warning("InboxWatcher is already running.")
            return

        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"InboxWatcher started (polling every {self.poll_interval}s).")

    def stop(self):
        """Stop the background watcher."""
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("InboxWatcher stopped.")

    def get_status(self) -> Dict[str, Any]:
        """Return the current watcher status and recent event logs."""
        return {
            "is_running": self.is_running,
            "poll_interval_seconds": self.poll_interval,
            "processed_count": len(self._processed_message_ids),
            "events_history": self.events_history[-20:],
            "last_check": datetime.now(timezone.utc).isoformat()
        }

    def _run_loop(self):
        """Continuous polling loop."""
        while self.is_running:
            try:
                self.check_for_inquiries()
            except Exception as e:
                logger.error(f"Error in InboxWatcher poll loop: {e}")
            
            # Sleep in small slices to allow fast shutdown
            for _ in range(self.poll_interval):
                if not self.is_running:
                    break
                time.sleep(1)

    def check_for_inquiries(self) -> List[Dict[str, Any]]:
        """
        Polls Gmail for unread inquiries or project requests.
        Returns list of newly processed workflows.
        """
        query = 'is:unread (subject:inquiry OR subject:project OR subject:proposal OR subject:quote OR subject:freelance OR "build" OR "budget" OR "hire")'
        try:
            res = self.gmail.run(action="search_emails", query=query, max_results=10)
            emails = res.get("emails", [])
        except Exception as e:
            logger.warning(f"Could not search Gmail: {e}")
            return []

        processed_plans = []
        for em in emails:
            msg_id = em.get("id")
            if not msg_id or msg_id in self._processed_message_ids:
                continue

            self._processed_message_ids.add(msg_id)
            logger.info(f"🎯 New Client Inquiry Detected! ID={msg_id} From={em.get('from')} Subject={em.get('subject')}")

            # Read full body
            full_msg = self.gmail.run(action="read_email", message_id=msg_id)
            body_text = full_msg.get("body") or em.get("snippet") or ""

            # Trigger autonomous coordinator
            plan = self.process_inquiry(
                sender=em.get("from", "Client"),
                subject=em.get("subject", "Project Inquiry"),
                body=body_text,
                date=em.get("date", datetime.now().isoformat()),
                source="GMAIL"
            )
            if plan:
                processed_plans.append(plan)

        return processed_plans

    def process_inquiry(
        self,
        sender: str,
        subject: str,
        body: str,
        date: Optional[str] = None,
        source: str = "SIMULATION"
    ) -> WorkflowPlan:
        """
        Takes an inquiry payload, creates an autonomous multi-app workflow goal,
        and coordinates execution across Calendar, Docs, Sheets, and Gmail.
        """
        goal_text = (
            f"Coordinate new freelance client inquiry from '{sender}'.\n"
            f"Subject: '{subject}'\n"
            f"Message: {body}\n"
            f"Autonomous Objectives:\n"
            f"1. Check Google Calendar for availability and schedule a 45-minute Kickoff/Discovery call.\n"
            f"2. Generate a comprehensive Statement of Work (SOW) & Proposal in Google Docs with deliverables and timeline.\n"
            f"3. Append this lead to the Google Sheets Client Pipeline CRM with status 'PROPOSAL_DRAFTED' and link to the SOW.\n"
            f"4. Prepare a personalized email response draft in Gmail confirming receipt and including the discovery call time.\n"
            f"5. Validate deliverable integrity."
        )

        event_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "sender": sender,
            "subject": subject,
            "snippet": body[:150] + "..." if len(body) > 150 else body,
            "status": "PROCESSING"
        }
        self.events_history.append(event_record)

        logger.info(f"Triggering Taskmaster Orchestrator for goal: {goal_text[:120]}...")
        task_goal = TaskGoal(
            goal=goal_text,
            context={
                "inquiry_sender": sender,
                "inquiry_subject": subject,
                "inquiry_body": body,
                "inquiry_date": date or datetime.now(timezone.utc).isoformat(),
                "workflow_type": "FREELANCE_PIPELINE_COORDINATOR"
            }
        )

        plan = self.orchestrator.create_plan(task_goal)
        executed_plan = self.orchestrator.execute_workflow(plan.workflow_id)

        event_record["status"] = executed_plan.status.value
        event_record["workflow_id"] = executed_plan.workflow_id
        event_record["summary"] = executed_plan.summary

        return executed_plan


# Global singleton instance
watcher = InboxWatcher(poll_interval_seconds=30)
