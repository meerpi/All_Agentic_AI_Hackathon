"""
Base Sub-Agent and Inter-Agent Communication Protocol.

Standardized internal messaging for the 5-Agent Council.
(For external Agent2Agent Linux Foundation standard communication, see agent.a2a).
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SubAgentRole(str, Enum):
    ORCHESTRATOR = "Meta-Orchestrator"
    INTELLIGENCE = "Intelligence & Intake Specialist"
    ENGINEERING = "Technical Product Owner & Jira Lead"
    EXECUTIVE_DOC = "Executive Communications & Documentation Lead"
    OPERATIONS = "Logistics & Workflow Coordinator"
    CRITIC = "Quality & Compliance Auditor"


class InterAgentMessage(BaseModel):
    """Standardized message packet passed between council sub-agents."""
    message_id: str
    sender_role: SubAgentRole
    recipient_role: SubAgentRole
    content: str
    context_data: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# Alias for backward compatibility
A2AMessage = InterAgentMessage


class AgentResponse(BaseModel):
    """Structured response from a specialized sub-agent."""
    agent_name: str
    role: SubAgentRole
    status: str = "SUCCESS"  # SUCCESS, FAILED, NEEDS_REVISION
    reasoning: str
    insights: Dict[str, Any] = Field(default_factory=dict)
    artifacts_created: List[Dict[str, Any]] = Field(default_factory=list)
    execution_time_ms: float = 0.0
    tool_calls_executed: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BaseSubAgent(ABC):
    """Abstract base class for all specialized domain sub-agents."""

    def __init__(
        self,
        agent_id: str,
        name: str,
        role: SubAgentRole,
        description: str,
        system_prompt: str,
        scoped_tool_names: List[str]
    ):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.description = description
        self.system_prompt = system_prompt
        self.scoped_tool_names = scoped_tool_names

    @abstractmethod
    def execute(self, task_payload: Dict[str, Any], accumulated_context: Dict[str, Any]) -> AgentResponse:
        """Execute the subagent's domain responsibility."""
        pass

    def process_message(self, message: InterAgentMessage) -> AgentResponse:
        """Process an incoming InterAgentMessage."""
        return self.execute(
            task_payload={"content": message.content, "artifacts": message.artifacts},
            accumulated_context=message.context_data,
        )
