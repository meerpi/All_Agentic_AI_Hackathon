"""
Agent2Agent (A2A) Standard Protocol — AgentCard Manifest.

Conforms to the Google / Linux Foundation A2A Specification (2025/2026).
Served at `/.well-known/agent-card.json` for external agent discovery.
"""

from typing import Any, Dict, List


def get_agent_card(base_url: str = "http://localhost:8000") -> Dict[str, Any]:
    """Return the official AgentCard JSON manifest according to A2A specification."""
    return {
        "$schema": "https://a2a-protocol.org/schemas/v1/agent-card.json",
        "protocol_version": "1.0",
        "name": "Taskmaster Autonomous Agent Council",
        "description": "Autonomous event-driven workflow engine with 5-agent hierarchical council, Jira, Google Workspace, Slack, DAG execution, and persistent memory.",
        "url": f"{base_url}/api/a2a",
        "version": "2.0.0",
        "provider": {
            "name": "Taskmaster AI Team",
            "url": "https://github.com/meerpi/curr_project/aihack",
        },
        "capabilities": {
            "streaming": True,
            "human_in_the_loop": True,
            "persistent_state": True,
            "task_cancellation": True,
            "complex_dag_orchestration": True,
        },
        "skills": [
            {
                "id": "workflow_planning",
                "name": "Autonomous Workflow Planning",
                "description": "Decomposes complex human instructions into DAGs with dependency ordering and Fibonacci complexity scores.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string", "description": "High level operational goal"},
                        "require_approval": {"type": "boolean", "default": False},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["goal"],
                },
            },
            {
                "id": "jira_sprint_management",
                "name": "Jira Agile Task Management",
                "description": "Creates, updates, and tracks Jira Cloud issues, story points, and sprint backlogs.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["create", "search", "update", "list_sprint"]},
                        "summary": {"type": "string"},
                        "issue_type": {"type": "string"},
                        "priority": {"type": "string"},
                    },
                    "required": ["action"],
                },
            },
            {
                "id": "google_workspace_sync",
                "name": "Google Workspace Multi-App Sync",
                "description": "Dispatches emails via Gmail, logs data to Google Sheets, creates Google Docs, and schedules Google Calendar meetings.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "service": {"type": "string", "enum": ["gmail", "docs", "sheets", "calendar"]},
                        "payload": {"type": "object"},
                    },
                    "required": ["service", "payload"],
                },
            },
            {
                "id": "prd_decomposition",
                "name": "PRD Requirements Parser",
                "description": "Ingests full PRD Markdown/Text documents and builds structured executable task graphs with dependencies.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "prd_content": {"type": "string"},
                    },
                    "required": ["prd_content"],
                },
            },
            {
                "id": "council_dispatch",
                "name": "5-Agent Council Deliberation",
                "description": "Executes 5 specialized sub-agents with A2A protocol and Reflexion loop scoring.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task_brief": {"type": "string"},
                    },
                    "required": ["task_brief"],
                },
            },
        ],
        "authentication": {
            "type": "none",
            "description": "Public local hackathon endpoint",
        },
    }
