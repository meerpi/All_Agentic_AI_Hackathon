"""
Workflow State Persistence & Checkpoint/Resume Engine.

Provides:
- JSON-file-backed workflow store under data/workflows/
- Checkpoint saving before each step execution
- Resume from checkpoint after server restart
- Workflow history archive for completed workflows
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("taskmaster.persistence")

WORKFLOWS_DIR = Path(__file__).parent.parent / "data" / "workflows"
CHECKPOINTS_DIR = Path(__file__).parent.parent / "data" / "checkpoints"
WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)


class WorkflowPersistence:
    """Persists workflows and checkpoints to disk for crash recovery."""

    def save_workflow(self, workflow_id: str, workflow_data: Dict[str, Any]):
        """Save the full workflow state to disk."""
        filepath = WORKFLOWS_DIR / f"{workflow_id}.json"
        with open(filepath, "w") as f:
            json.dump(workflow_data, f, indent=2, default=str)
        logger.debug(f"Saved workflow {workflow_id} to {filepath}")

    def load_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Load a workflow from disk."""
        filepath = WORKFLOWS_DIR / f"{workflow_id}.json"
        if filepath.exists():
            with open(filepath, "r") as f:
                return json.load(f)
        return None

    def list_workflows(self, status_filter: Optional[str] = None,
                       tag_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all persisted workflows, with optional filtering."""
        workflows = []
        for f in WORKFLOWS_DIR.glob("*.json"):
            try:
                with open(f, "r") as fh:
                    data = json.load(fh)
                    if status_filter and data.get("status") != status_filter:
                        continue
                    if tag_filter and tag_filter not in data.get("tags", []):
                        continue
                    workflows.append(data)
            except Exception as e:
                logger.warning(f"Failed to read {f}: {e}")
        # Sort by created_at descending
        workflows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return workflows

    def delete_workflow(self, workflow_id: str):
        """Delete a workflow from disk."""
        filepath = WORKFLOWS_DIR / f"{workflow_id}.json"
        if filepath.exists():
            filepath.unlink()

    # ── Checkpointing ──────────────────────────────────────────

    def save_checkpoint(self, workflow_id: str, step_number: int,
                        state: Dict[str, Any]):
        """Save a checkpoint before executing a step."""
        checkpoint = {
            "workflow_id": workflow_id,
            "step_number": step_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "state": state,
        }
        # Save indexed checkpoints for time-travel
        cp_dir = CHECKPOINTS_DIR / workflow_id
        cp_dir.mkdir(parents=True, exist_ok=True)
        filepath = cp_dir / f"step_{step_number}.json"
        with open(filepath, "w") as f:
            json.dump(checkpoint, f, indent=2, default=str)
        logger.debug(f"Checkpoint saved: {workflow_id} step {step_number}")

    def load_checkpoint(self, workflow_id: str,
                        step_number: Optional[int] = None) -> Optional[Dict]:
        """
        Load a checkpoint. If step_number is None, load the latest.
        """
        cp_dir = CHECKPOINTS_DIR / workflow_id
        if not cp_dir.exists():
            return None

        if step_number is not None:
            filepath = cp_dir / f"step_{step_number}.json"
            if filepath.exists():
                with open(filepath, "r") as f:
                    return json.load(f)
            return None

        # Find latest checkpoint
        checkpoints = sorted(cp_dir.glob("step_*.json"))
        if checkpoints:
            with open(checkpoints[-1], "r") as f:
                return json.load(f)
        return None

    def list_checkpoints(self, workflow_id: str) -> List[Dict]:
        """List all checkpoints for a workflow (for time-travel debugging)."""
        cp_dir = CHECKPOINTS_DIR / workflow_id
        if not cp_dir.exists():
            return []

        checkpoints = []
        for f in sorted(cp_dir.glob("step_*.json")):
            try:
                with open(f, "r") as fh:
                    checkpoints.append(json.load(fh))
            except Exception:
                pass
        return checkpoints

    def get_incomplete_workflows(self) -> List[Dict[str, Any]]:
        """Find workflows that were executing when the server stopped."""
        incomplete = []
        for data in self.list_workflows():
            if data.get("status") in ("EXECUTING", "PAUSED", "AWAITING_APPROVAL"):
                incomplete.append(data)
        return incomplete


# Global singleton
persistence = WorkflowPersistence()
