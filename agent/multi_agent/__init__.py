"""
Multi-Agent Council Package.
Hierarchical Multi-Agent System (MAS) architecture for Taskmaster.
"""

from agent.multi_agent.base_agent import BaseSubAgent, A2AMessage, AgentResponse, SubAgentRole
from agent.multi_agent.sub_agents import (
    IntelligenceSubAgent,
    EngineeringSubAgent,
    ExecutiveDocSubAgent,
    OperationsSubAgent,
    CriticSubAgent,
)
from agent.multi_agent.council_orchestrator import (
    MultiAgentCouncilOrchestrator,
    CouncilExecutionResult,
    CouncilDialogueEvent,
)

__all__ = [
    "BaseSubAgent",
    "A2AMessage",
    "AgentResponse",
    "SubAgentRole",
    "IntelligenceSubAgent",
    "EngineeringSubAgent",
    "ExecutiveDocSubAgent",
    "OperationsSubAgent",
    "CriticSubAgent",
    "MultiAgentCouncilOrchestrator",
    "CouncilExecutionResult",
    "CouncilDialogueEvent",
]
