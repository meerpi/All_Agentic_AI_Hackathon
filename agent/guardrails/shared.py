import logging
from agent.guardrails import check_input_rails
from agent.security import requires_approval, mask_pii

logger = logging.getLogger("taskmaster.bot_guardrails")

def apply_bot_guardrails(user_message: str = None, workflow_plan = None, output: str = None) -> str:
    """
    Shared function to enforce bot guardrails.
    - Runs check_input_rails on user_message.
    - Checks HITL requirements on workflow_plan via requires_approval.
    - Applies PII masking via mask_pii on output.
    """
    if user_message:
        rails = check_input_rails(user_message)
        if not rails.passed:
            raise ValueError(f"Input rejected by safety rails: {', '.join(rails.violations)}")
            
    if workflow_plan:
        for step in workflow_plan.steps:
            if requires_approval(step.tool_name, approval_mode=True):
                raise ValueError(f"Task requires human approval for tool '{step.tool_name}', which is not supported via bot.")
                
    if output:
        return mask_pii(output)
        
    return ""
