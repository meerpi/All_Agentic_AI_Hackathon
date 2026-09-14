"""
Strands Agents SDK Integration Bridge for Taskmaster Pro.

Provides model-driven autonomous workflows, tool adapters, Human-in-the-Loop governance,
and Multi-Agent Council Graph orchestration tailored for Track 2: Professional Agents.
"""

from agent.strands_bridge.hitl_intervention import (
    PendingApprovalRequest,
    TaskmasterHITLManager,
    hitl_manager,
)
from agent.strands_bridge.professional_agent import (
    PROFESSIONAL_SYSTEM_PROMPT,
    TaskmasterProAgent,
    build_professional_council_graph,
)
from agent.strands_bridge.preflight_auditor import (
    AuditRecord,
    PreFlightAuditor,
    preflight_auditor,
)
from agent.strands_bridge.tool_adapter import (
    SAFE_TOOLS,
    SENSITIVE_TOOLS,
    StrandsToolRegistry,
    adapt_basetool_to_strands,
    strands_tool_registry,
)

__all__ = [
    "AuditRecord",
    "PreFlightAuditor",
    "preflight_auditor",
    "PROFESSIONAL_SYSTEM_PROMPT",
    "PendingApprovalRequest",
    "SAFE_TOOLS",
    "SENSITIVE_TOOLS",
    "StrandsToolRegistry",
    "TaskmasterHITLManager",
    "TaskmasterProAgent",
    "adapt_basetool_to_strands",
    "build_professional_council_graph",
    "hitl_manager",
    "strands_tool_registry",
]
