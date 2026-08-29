import logging
import time
from datetime import datetime
from typing import Dict, List, Optional
from agent.config import settings
from agent.llm_client import GeminiClient
from agent.models import (
    ExecutionTrace,
    PlanStep,
    StepStatus,
    TaskGoal,
    ToolCallResult,
    WorkflowPlan,
    WorkflowStatus,
)
from agent.prompts import (
    FINAL_SUMMARY_PROMPT,
    PLANNING_PROMPT_TEMPLATE,
    SELF_CORRECTION_PROMPT,
    TASKMASTER_SYSTEM_PROMPT,
)
from agent.tools.registry import registry

logger = logging.getLogger("taskmaster.orchestrator")


class TaskmasterOrchestrator:
    def __init__(self):
        self.llm = GeminiClient()
        self.registry = registry
        self.workflows: Dict[str, WorkflowPlan] = {}
        self.traces: Dict[str, List[ExecutionTrace]] = {}

    def _add_trace(self, workflow_id: str, event_type: str, step_number: Optional[int] = None, details: Optional[Dict] = None):
        trace = ExecutionTrace(
            workflow_id=workflow_id,
            event_type=event_type,
            step_number=step_number,
            details=details or {}
        )
        if workflow_id not in self.traces:
            self.traces[workflow_id] = []
        self.traces[workflow_id].append(trace)
        logger.info(f"[{workflow_id}] TRACE [{event_type}]: step={step_number} | {details}")

    def create_plan(self, goal_input: TaskGoal) -> WorkflowPlan:
        """Decomposes high-level goal into structured multi-step workflow plan via Gemini."""
        tools_desc = self.registry.get_tools_description_prompt()
        prompt = PLANNING_PROMPT_TEMPLATE.format(
            system_prompt=TASKMASTER_SYSTEM_PROMPT,
            goal=goal_input.goal,
            context=goal_input.context,
            tools_description=tools_desc
        )

        llm_response = self.llm.generate_json(prompt)
        raw_steps = llm_response.get("steps", [])

        plan_steps = []
        for idx, step_dict in enumerate(raw_steps, start=1):
            plan_steps.append(
                PlanStep(
                    step_number=idx,
                    description=step_dict.get("description", f"Step {idx}"),
                    tool_name=step_dict.get("tool_name", "data_extractor"),
                    tool_args=step_dict.get("tool_args", {}),
                    reasoning=step_dict.get("reasoning", "Agent selected tool for step execution"),
                    status=StepStatus.PENDING
                )
            )

        workflow = WorkflowPlan(
            goal=goal_input.goal,
            steps=plan_steps,
            status=WorkflowStatus.CREATED
        )
        
        self.workflows[workflow.workflow_id] = workflow
        self._add_trace(
            workflow.workflow_id,
            "PLAN_GENERATED",
            details={"step_count": len(plan_steps), "steps": [s.description for s in plan_steps]}
        )
        return workflow

    def execute_workflow(self, workflow_id: str) -> WorkflowPlan:
        """Executes workflow steps autonomously, handling retries, tool execution, and state persistence."""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow ID {workflow_id} not found.")

        workflow.status = WorkflowStatus.EXECUTING
        workflow.updated_at = datetime.utcnow()

        logger.info(f"Starting autonomous execution of workflow {workflow_id} with {len(workflow.steps)} steps.")

        accumulated_results = []

        for step in workflow.steps:
            workflow.current_step_index = step.step_number - 1
            step.status = StepStatus.IN_PROGRESS
            self._add_trace(workflow_id, "STEP_STARTED", step_number=step.step_number, details={"tool": step.tool_name})

            tool_instance = self.registry.get_tool(step.tool_name)
            if not tool_instance:
                step.status = StepStatus.FAILED
                step.error = f"Tool '{step.tool_name}' not registered in tool registry."
                self._add_trace(workflow_id, "STEP_FAILED", step_number=step.step_number, details={"error": step.error})
                continue

            # Execute tool
            tool_result: ToolCallResult = tool_instance.execute(**step.tool_args)
            step.execution_time_ms = tool_result.execution_time_ms

            if tool_result.success:
                step.status = StepStatus.COMPLETED
                step.result = tool_result.data
                accumulated_results.append({
                    "step": step.step_number,
                    "tool": step.tool_name,
                    "data": tool_result.data
                })
                self._add_trace(
                    workflow_id,
                    "TOOL_EXECUTION_SUCCESS",
                    step_number=step.step_number,
                    details={"tool": step.tool_name, "execution_ms": tool_result.execution_time_ms}
                )
            else:
                # Attempt Self-Correction
                logger.warning(f"Step {step.step_number} failed. Triggering Self-Correction Routine.")
                self._add_trace(workflow_id, "SELF_CORRECTION_TRIGGERED", step_number=step.step_number, details={"error": tool_result.error_message})
                
                corrected_result = self._attempt_self_correction(step, tool_result.error_message or "Tool execution error")
                if corrected_result.success:
                    step.status = StepStatus.COMPLETED
                    step.result = corrected_result.data
                    step.reasoning += " (Recovered via agent self-correction)"
                    accumulated_results.append({
                        "step": step.step_number,
                        "tool": step.tool_name,
                        "data": corrected_result.data
                    })
                    self._add_trace(workflow_id, "SELF_CORRECTION_SUCCESS", step_number=step.step_number)
                else:
                    step.status = StepStatus.FAILED
                    step.error = tool_result.error_message
                    self._add_trace(workflow_id, "STEP_FAILED", step_number=step.step_number, details={"error": step.error})

        # Synthesize Final Report
        workflow.status = WorkflowStatus.COMPLETED
        workflow.updated_at = datetime.utcnow()

        summary_prompt = FINAL_SUMMARY_PROMPT.format(
            goal=workflow.goal,
            steps_summary="\n".join([f"- Step {s.step_number}: {s.description} ({s.status.value})" for s in workflow.steps]),
            artifacts_summary=str(accumulated_results)
        )
        
        summary_response = self.llm.generate_json(summary_prompt)
        workflow.summary = summary_response.get("summary_markdown", "Task workflow executed successfully.")
        workflow.final_artifact = {
            "summary_markdown": workflow.summary,
            "key_takeaways": summary_response.get("key_takeaways", []),
            "step_results": accumulated_results
        }

        self._add_trace(workflow_id, "WORKFLOW_FINISHED", details={"status": workflow.status.value})
        return workflow

    def _attempt_self_correction(self, step: PlanStep, error_msg: str) -> ToolCallResult:
        """Invokes LLM self-correction logic to re-parameterize and retry tool call."""
        correction_prompt = SELF_CORRECTION_PROMPT.format(
            step_number=step.step_number,
            tool_name=step.tool_name,
            error_details=error_msg,
            step_context=step.description,
            history=""
        )
        llm_fix = self.llm.generate_json(correction_prompt)
        new_args = llm_fix.get("tool_args", step.tool_args)

        tool_instance = self.registry.get_tool(step.tool_name)
        if tool_instance:
            return tool_instance.execute(**new_args)
        
        return ToolCallResult(tool_name=step.tool_name, success=False, error_message="Self correction tool look up failed")

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowPlan]:
        return self.workflows.get(workflow_id)

    def get_traces(self, workflow_id: str) -> List[ExecutionTrace]:
        return self.traces.get(workflow_id, [])
