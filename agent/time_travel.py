"""
Time-Travel Debugging Engine.

Allows developers and operators to:
1. Inspect the full checkpoint state history of a workflow
2. Replay execution from an earlier checkpoint
3. Fork a new workflow branch from an earlier checkpoint with modified state/arguments
"""

import copy
import logging
import uuid
from typing import Any, Dict, List, Optional
from agent.persistence import persistence
from agent.models import WorkflowPlan, StepStatus, WorkflowStatus

logger = logging.getLogger("taskmaster.time_travel")


class TimeTravelEngine:
    """Provides snapshot traversal, replay, and state forking."""

    def get_history(self, workflow_id: str) -> List[Dict[str, Any]]:
        """Get the chronological sequence of checkpoints for a workflow."""
        return persistence.list_checkpoints(workflow_id)

    def fork_from_checkpoint(self, original_workflow_id: str, checkpoint_step_number: int,
                             modified_inputs: Optional[Dict[str, Any]] = None) -> WorkflowPlan:
        """
        Fork a new workflow branch from a specific checkpoint, applying optional state overrides.
        """
        checkpoint = persistence.load_checkpoint(original_workflow_id, checkpoint_step_number)
        if not checkpoint:
            raise ValueError(f"Checkpoint for step {checkpoint_step_number} in workflow {original_workflow_id} not found.")

        state = checkpoint.get("state", {})
        new_workflow_id = str(uuid.uuid4())

        # Clone and reset downstream steps
        plan_data = copy.deepcopy(state)
        plan_data["workflow_id"] = new_workflow_id
        plan_data["status"] = WorkflowStatus.CREATED.value
        plan_data["context_id"] = f"fork_of_{original_workflow_id[:8]}"
        plan_data["tags"] = plan_data.get("tags", []) + [f"fork:{original_workflow_id[:6]}"]

        # Reset steps after the checkpoint
        for step in plan_data.get("steps", []):
            if step["step_number"] >= checkpoint_step_number:
                step["status"] = StepStatus.PENDING.value
                step["result"] = None
                step["error"] = None
                if modified_inputs and step["step_number"] == checkpoint_step_number:
                    step["tool_args"].update(modified_inputs)

        forked_plan = WorkflowPlan(**plan_data)
        persistence.save_workflow(new_workflow_id, forked_plan.model_dump(mode="json"))

        logger.info(f"Forked workflow {original_workflow_id} at step {checkpoint_step_number} -> {new_workflow_id}")
        return forked_plan


time_travel = TimeTravelEngine()
