import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WAITING_APPROVAL = "WAITING_APPROVAL"


class WorkflowStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"


class TaskGoal(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = Field(..., description="High-level operational goal for the taskmaster agent")
    context: Dict[str, Any] = Field(default_factory=dict, description="Optional payload, files, or environment parameters")
    require_approval: bool = Field(default=False, description="Whether sensitive tool actions require human confirmation")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PlanStep(BaseModel):
    step_number: int = Field(..., description="1-indexed step order")
    description: str = Field(..., description="High-level step goal")
    tool_name: str = Field(..., description="Tool to execute for this step")
    tool_args: Dict[str, Any] = Field(default_factory=dict, description="Structured arguments for the tool")
    reasoning: str = Field(..., description="Agent reasoning explaining why this tool and arguments were chosen")
    status: StepStatus = Field(default=StepStatus.PENDING)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None


class WorkflowPlan(BaseModel):
    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str
    steps: List[PlanStep] = Field(default_factory=list)
    status: WorkflowStatus = Field(default=WorkflowStatus.CREATED)
    current_step_index: int = Field(default=0)
    final_artifact: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ToolCallResult(BaseModel):
    tool_name: str
    success: bool
    data: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0


class ExecutionTrace(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str = Field(..., description="e.g. PLAN_GENERATED, STEP_STARTED, TOOL_EXECUTION, SELF_CORRECTION, COMPLETED")
    step_number: Optional[int] = None
    details: Dict[str, Any] = Field(default_factory=dict)
