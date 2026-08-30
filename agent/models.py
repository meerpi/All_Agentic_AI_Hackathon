"""
Taskmaster Agent Data Models — Production-Grade.

Supports: Task dependency DAG, subtask expansion, complexity scoring,
tagged multi-context task lists, token/cost tracking, checkpoint/resume,
human-in-the-loop approval gates, and structured evaluation.
"""

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
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class WorkflowStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ── Token / Cost Tracking ──────────────────────────────────────

class TokenUsage(BaseModel):
    """Token usage for a single LLM call."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_used: str = ""
    estimated_cost_usd: float = 0.0


class WorkflowTokenUsage(BaseModel):
    """Aggregate token usage across an entire workflow."""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_estimated_cost_usd: float = 0.0
    calls: List[TokenUsage] = Field(default_factory=list)

    def add(self, usage: TokenUsage):
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        self.total_estimated_cost_usd += usage.estimated_cost_usd
        self.calls.append(usage)


# ── Task / Goal Models ─────────────────────────────────────────

class TaskGoal(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = Field(..., description="High-level operational goal for the taskmaster agent")
    context: Dict[str, Any] = Field(default_factory=dict, description="Optional payload, files, or environment parameters")
    require_approval: bool = Field(default=False, description="Whether sensitive tool actions require human confirmation")
    tags: List[str] = Field(default_factory=list, description="Tags for multi-context task list isolation (e.g. 'feature-auth', 'sprint-43')")
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Plan Step (DAG-aware) ──────────────────────────────────────

class PlanStep(BaseModel):
    step_number: int = Field(..., description="1-indexed step order")
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for DAG referencing")
    description: str = Field(..., description="High-level step goal")
    tool_name: str = Field(..., description="Tool to execute for this step")
    tool_args: Dict[str, Any] = Field(default_factory=dict, description="Structured arguments for the tool")
    reasoning: str = Field(..., description="Agent reasoning explaining why this tool and arguments were chosen")
    status: StepStatus = Field(default=StepStatus.PENDING)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None

    # DAG dependency support
    depends_on: List[int] = Field(default_factory=list, description="List of step_numbers this step depends on (must complete first)")

    # Subtask expansion
    subtasks: List["PlanStep"] = Field(default_factory=list, description="Child subtasks from expansion")
    is_expanded: bool = Field(default=False, description="Whether this step has been expanded into subtasks")

    # Complexity scoring
    complexity_score: Optional[int] = Field(default=None, description="Fibonacci complexity score (1,2,3,5,8,13,21)")
    complexity_reasoning: Optional[str] = Field(default=None, description="Why this complexity score was assigned")

    # Risk classification for HITL gating
    risk_level: RiskLevel = Field(default=RiskLevel.LOW)

    # Token tracking per step
    token_usage: Optional[TokenUsage] = None


# Allow recursive subtask nesting
PlanStep.model_rebuild()


# ── Workflow Plan ──────────────────────────────────────────────

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

    # HITL approval mode — when True, HIGH/CRITICAL tools pause for human confirmation
    require_approval: bool = Field(default=False)

    # Tagged multi-context task lists
    tags: List[str] = Field(default_factory=list, description="Tags for context isolation (e.g. 'feature-auth')")
    context_id: Optional[str] = Field(default=None, description="Context group identifier")

    # Token / cost tracking
    token_usage: WorkflowTokenUsage = Field(default_factory=WorkflowTokenUsage)

    # Checkpoint / resume
    checkpoint_data: Optional[Dict[str, Any]] = Field(default=None, description="Serialized state for pause/resume")
    paused_at_step: Optional[int] = Field(default=None, description="Step number where workflow was paused")

    # Evaluation scores
    eval_scores: Optional[Dict[str, Any]] = Field(default=None, description="Structured eval scores (plan_quality, plan_adherence, tool_selection)")



# ── Tool Call Result ───────────────────────────────────────────

class ToolCallResult(BaseModel):
    tool_name: str
    success: bool
    data: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0


# ── Execution Trace ────────────────────────────────────────────

class ExecutionTrace(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str = Field(..., description="e.g. PLAN_GENERATED, STEP_STARTED, TOOL_EXECUTION, SELF_CORRECTION, COMPLETED, CHECKPOINT_SAVED, HITL_PAUSE, GUARDRAIL_BLOCK")
    step_number: Optional[int] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    token_usage: Optional[TokenUsage] = None


# ── Complexity Report ──────────────────────────────────────────

class ComplexityReport(BaseModel):
    """Output of complexity analysis for a workflow."""
    workflow_id: str
    total_steps: int
    total_complexity_points: int = 0
    avg_complexity: float = 0.0
    critical_path_length: int = 0
    parallelizable_groups: int = 0
    step_scores: List[Dict[str, Any]] = Field(default_factory=list)
    bottleneck_steps: List[int] = Field(default_factory=list, description="Step numbers with highest complexity")
