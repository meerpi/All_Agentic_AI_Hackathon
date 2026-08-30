"""
Hierarchical Multi-Agent Council Orchestrator (Leader-Subagent Pattern).
Orchestrates topological execution, inter-agent A2A message routing,
reflection/audit loops, and live dialogue logging.
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agent.llm_client import GeminiClient
from agent.multi_agent.base_agent import A2AMessage, AgentResponse, SubAgentRole
from agent.multi_agent.sub_agents import (
    IntelligenceSubAgent,
    EngineeringSubAgent,
    ExecutiveDocSubAgent,
    OperationsSubAgent,
    CriticSubAgent,
)

logger = logging.getLogger("taskmaster.multi_agent.orchestrator")


class CouncilDialogueEvent(BaseModel):
    """Event representing inter-agent dialogue in the Multi-Agent Council."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender: str
    sender_role: str
    recipient: str
    message: str
    artifacts_attached: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CouncilExecutionResult(BaseModel):
    """Aggregate result from the Multi-Agent Council execution."""
    workflow_id: str
    goal: str
    status: str = "COMPLETED"
    total_execution_time_ms: float = 0.0
    council_dialogue: List[CouncilDialogueEvent] = Field(default_factory=list)
    subagent_responses: List[AgentResponse] = Field(default_factory=list)
    all_artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    executive_summary: str = ""


class MultiAgentCouncilOrchestrator:
    """Lead Orchestrator coordinating the 5-Agent Council."""

    def __init__(self, llm_client: Optional[GeminiClient] = None):
        self.llm = llm_client or GeminiClient()
        self.intelligence_agent = IntelligenceSubAgent(self.llm)
        self.engineering_agent = EngineeringSubAgent(self.llm)
        self.executive_doc_agent = ExecutiveDocSubAgent(self.llm)
        self.operations_agent = OperationsSubAgent(self.llm)
        self.critic_agent = CriticSubAgent(self.llm)

    def execute_council(self, goal: str, context: Optional[Dict[str, Any]] = None) -> CouncilExecutionResult:
        """Run the full hierarchical multi-agent council workflow."""
        start_time = time.time()
        workflow_id = str(uuid.uuid4())
        context = context or {}

        dialogue: List[CouncilDialogueEvent] = []
        responses: List[AgentResponse] = []
        all_artifacts: List[Dict[str, Any]] = []
        accumulated_context: Dict[str, Any] = {"goal": goal, "context": context}

        def record_dialogue(sender: str, role: str, recipient: str, message: str, artifacts: Optional[List[Dict[str, Any]]] = None):
            event = CouncilDialogueEvent(
                sender=sender,
                sender_role=role,
                recipient=recipient,
                message=message,
                artifacts_attached=artifacts or []
            )
            dialogue.append(event)
            logger.info(f"[{role} ➔ {recipient}]: {message[:120]}...")

        # 0. Orchestrator Kickoff
        record_dialogue(
            sender="Meta-Orchestrator",
            role=SubAgentRole.ORCHESTRATOR.value,
            recipient="Intelligence & Intake Specialist",
            message=f"Council initialized for goal: '{goal[:100]}...'. Initiating Stage 1: Intelligence Analysis & Entity Resolution."
        )

        # Stage 1: Intelligence Sub-Agent
        intel_task = {"goal": goal, "transcript": context.get("transcript", goal), "raw_text": context.get("raw_text", goal)}
        intel_resp = self.intelligence_agent.execute(intel_task, accumulated_context)
        responses.append(intel_resp)
        all_artifacts.extend(intel_resp.artifacts_created)
        accumulated_context["intelligence_insights"] = intel_resp.insights

        record_dialogue(
            sender=self.intelligence_agent.name,
            role=self.intelligence_agent.role.value,
            recipient="Technical Product Owner & Jira Lead",
            message=f"Extracted {len(intel_resp.insights.get('action_items', []))} action items from input transcript. Handing off to Engineering for Fibonacci sizing & Jira Cloud ticket creation.",
            artifacts=intel_resp.artifacts_created
        )

        # Stage 2: Engineering Sub-Agent
        eng_task = {"action_items": intel_resp.insights.get("action_items", [])}
        eng_resp = self.engineering_agent.execute(eng_task, accumulated_context)
        responses.append(eng_resp)
        all_artifacts.extend(eng_resp.artifacts_created)
        accumulated_context["engineering_insights"] = eng_resp.insights

        record_dialogue(
            sender=self.engineering_agent.name,
            role=self.engineering_agent.role.value,
            recipient="Executive Communications Lead",
            message=f"Provisioned {len(eng_resp.insights.get('tickets', []))} Jira Cloud tickets ({', '.join(eng_resp.insights.get('issue_keys', []))}) totaling {eng_resp.insights.get('total_story_points', 0)} story points. Handing off for executive synthesis.",
            artifacts=eng_resp.artifacts_created
        )

        # Stage 3: Executive Documentation Sub-Agent
        doc_task = {"meeting_title": intel_resp.insights.get("meeting_title", "Executive Sprint Planning")}
        doc_resp = self.executive_doc_agent.execute(doc_task, accumulated_context)
        responses.append(doc_resp)
        all_artifacts.extend(doc_resp.artifacts_created)
        accumulated_context["doc_insights"] = doc_resp.insights

        record_dialogue(
            sender=self.executive_doc_agent.name,
            role=self.executive_doc_agent.role.value,
            recipient="Operations & Workflow Coordinator",
            message=f"Published Executive Meeting Minutes to Google Docs and formatted Slack announcement. Requesting Operations Agent to sync Sprint Backlog to Google Sheets.",
            artifacts=doc_resp.artifacts_created
        )

        # Stage 4: Operations Sub-Agent
        ops_task = {"meeting_title": intel_resp.insights.get("meeting_title", "Sprint 42 Backlog")}
        ops_resp = self.operations_agent.execute(ops_task, accumulated_context)
        responses.append(ops_resp)
        all_artifacts.extend(ops_resp.artifacts_created)
        accumulated_context["ops_insights"] = ops_resp.insights

        record_dialogue(
            sender=self.operations_agent.name,
            role=self.operations_agent.role.value,
            recipient="Quality & Compliance Auditor",
            message=f"Sprint Backlog created and populated in Google Sheets ({ops_resp.insights.get('total_rows_synced', 0)} rows). Submitting full artifact suite for compliance & consistency audit.",
            artifacts=ops_resp.artifacts_created
        )

        # Stage 5: Critic & Compliance Sub-Agent (Reflexion Loop)
        critic_task = {}
        critic_resp = self.critic_agent.execute(critic_task, accumulated_context)
        responses.append(critic_resp)
        all_artifacts.extend(critic_resp.artifacts_created)

        audit_verdict = critic_resp.insights.get('verdict', 'PASSED')
        audit_score = critic_resp.insights.get('audit_score', 100)
        violations = critic_resp.insights.get('violations', [])
        audit_detail = "All deliverables certified consistent across Jira Cloud and Google Workspace." if not violations else f"Detected {len(violations)} violations: {'; '.join(violations)}"

        record_dialogue(
            sender=self.critic_agent.name,
            role=self.critic_agent.role.value,
            recipient="Meta-Orchestrator",
            message=f"Audit Verdict: {audit_verdict} (Score: {audit_score}/100, Violations: {len(violations)}). {audit_detail}",
            artifacts=critic_resp.artifacts_created
        )

        total_elapsed = (time.time() - start_time) * 1000

        # Compile Executive Summary
        doc_url = accumulated_context.get("doc_insights", {}).get("document_url", "")
        sheet_url = accumulated_context.get("ops_insights", {}).get("spreadsheet_url", "")
        jira_keys = accumulated_context.get("engineering_insights", {}).get("issue_keys", [])
        audit_score = critic_resp.insights.get("audit_score", 100)
        violations_count = len(critic_resp.insights.get("violations", []))
        verdict = critic_resp.insights.get("verdict", "PASSED")

        summary = f"""# 🏛️ Multi-Agent Council Execution Report

The **Taskmaster Hierarchical Multi-Agent Council** executed the assigned goal across 5 specialized sub-agents. Audit status: **{verdict}**.

### 👥 Sub-Agent Contributions:
1. **🔍 Intelligence & Intake Specialist**: Analyzed raw inputs and extracted {len(intel_resp.insights.get('action_items', []))} core action items.
2. **⚡ Technical Product Owner**: Provisioned {len(jira_keys)} Jira Cloud tickets ({', '.join(jira_keys)}) totaling {accumulated_context.get('engineering_insights', {}).get('total_story_points', 0)} story points.
3. **📄 Executive Communications Lead**: Authored Executive Meeting Minutes and dispatched Slack announcement.
4. **📅 Operations Coordinator**: Created and synced the Sprint Backlog Google Sheet ({accumulated_context.get('ops_insights', {}).get('total_rows_synced', 0)} rows).
5. **🛡️ Quality & Compliance Auditor**: Certified artifacts with a **{audit_score}/100 Audit Score ({violations_count} Violations)**.

### 🔗 Live Artifact Links:
- 🎫 **Jira Cloud Tickets:** {', '.join(jira_keys)}
- 📄 **Google Doc Minutes:** {doc_url}
- 📊 **Google Sheets Backlog:** {sheet_url}
"""

        return CouncilExecutionResult(
            workflow_id=workflow_id,
            goal=goal,
            status="COMPLETED" if verdict == "PASSED" else "NEEDS_REVISION",
            total_execution_time_ms=round(total_elapsed, 2),
            council_dialogue=dialogue,
            subagent_responses=responses,
            all_artifacts=all_artifacts,
            executive_summary=summary
        )

    def dispatch(self, brief: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """A2A protocol dispatch entrypoint."""
        result = self.execute_council(goal=brief, context=context)
        return result.model_dump(mode="json")


# Alias for backward compatibility
CouncilOrchestrator = MultiAgentCouncilOrchestrator
