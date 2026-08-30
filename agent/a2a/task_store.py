"""
Agent2Agent (A2A) Standard Protocol — 8-State Task Lifecycle Store.

States:
- submitted: Received by the agent
- working: Currently being processed
- input-required: Paused, waiting for client/human input
- completed: Finished successfully with artifacts
- failed: Encountered an error
- canceled: Terminated by client
- unknown: State not available
- expired: Time-to-live elapsed
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class A2ATaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    UNKNOWN = "unknown"
    EXPIRED = "expired"


class A2AArtifact(BaseModel):
    name: str
    mime_type: str = "application/json"
    data: Any


class A2ATask(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    skill_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    state: A2ATaskState = Field(default=A2ATaskState.SUBMITTED)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    artifacts: List[A2AArtifact] = Field(default_factory=list)
    error_message: Optional[str] = None
    input_prompt: Optional[str] = None  # Populated when state is input-required
    workflow_id: Optional[str] = None


class A2ATaskStore:
    """In-memory + disk-backed store for A2A protocol tasks."""

    def __init__(self):
        self._tasks: Dict[str, A2ATask] = {}

    def create_task(self, skill_id: str, parameters: Dict[str, Any]) -> A2ATask:
        task = A2ATask(skill_id=skill_id, parameters=parameters)
        self._tasks[task.task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[A2ATask]:
        return self._tasks.get(task_id)

    def update_state(self, task_id: str, new_state: A2ATaskState, error: Optional[str] = None) -> Optional[A2ATask]:
        task = self.get_task(task_id)
        if task:
            task.state = new_state
            task.updated_at = datetime.now(timezone.utc)
            if error:
                task.error_message = error
        return task

    def add_artifact(self, task_id: str, name: str, data: Any, mime_type: str = "application/json"):
        task = self.get_task(task_id)
        if task:
            task.artifacts.append(A2AArtifact(name=name, data=data, mime_type=mime_type))
            task.updated_at = datetime.now(timezone.utc)

    def cancel_task(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if task and task.state not in (A2ATaskState.COMPLETED, A2ATaskState.FAILED):
            task.state = A2ATaskState.CANCELED
            task.updated_at = datetime.now(timezone.utc)
            return True
        return False

    def list_tasks(self) -> List[A2ATask]:
        return list(self._tasks.values())


# Global A2A task store
a2a_task_store = A2ATaskStore()
