import logging
from typing import List, Optional
from agent.guardrails import check_input_rails
from agent.security import requires_approval, mask_pii

logger = logging.getLogger("taskmaster.bot_guardrails")

def apply_bot_guardrails(user_message: str = None, workflow_plan = None, output: str = None) -> str:
    """
    Shared function to enforce bot guardrails.
    - Runs check_input_rails on user_message.
    - Checks HITL requirements on workflow_plan via requires_approval.
      Instead of hard-aborting, sets require_approval=True on the workflow
      so the orchestrator pauses at AWAITING_APPROVAL for high-risk steps.
    - Applies PII masking via mask_pii on output.
    """
    if user_message:
        rails = check_input_rails(user_message)
        if not rails.passed:
            raise ValueError(f"Input rejected by safety rails: {', '.join(rails.violations)}")
            
    if workflow_plan:
        approval_needed_tools: List[str] = []
        for step in workflow_plan.steps:
            if requires_approval(step.tool_name, approval_mode=True):
                approval_needed_tools.append(step.tool_name)
        if approval_needed_tools:
            # Enable HITL approval on the workflow so the orchestrator will pause
            # instead of aborting entirely. The web dashboard /api/agent/approve/{workflow_id}
            # endpoint can be used to approve. Bot-side approval UI is added in Phase 5.
            workflow_plan.require_approval = True
            logger.info(
                f"Workflow {workflow_plan.workflow_id} requires HITL approval for tools: "
                f"{approval_needed_tools}. Setting require_approval=True for pause-at-execution."
            )
                
    if output:
        return mask_pii(output)
        
    return ""


def get_approval_required_tools(workflow_plan) -> List[str]:
    """Returns list of tool names in the workflow that require HITL approval."""
    if not workflow_plan:
        return []
    return [
        step.tool_name for step in workflow_plan.steps
        if requires_approval(step.tool_name, approval_mode=True)
    ]

