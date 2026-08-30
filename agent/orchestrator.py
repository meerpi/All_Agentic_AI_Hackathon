"""
Production-Grade Autonomous Taskmaster Orchestrator.

Integrates:
- Task Dependency DAG with Topological Execution
- Input, Execution, and Output Guardrails
- Real Human-in-the-Loop (HITL) approval pause/resume gates
- Persistent Checkpointing (data/checkpoints/ and data/workflows/)
- Token usage & cost tracking aggregation
- Multi-dimensional Trajectory Evaluation (DeepEval style)
- Persistent 3-tier Memory integration (Episodic, Semantic, Procedural)
- Enhanced Self-Correction with alternative tool suggestions & exponential backoff
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from agent.config import settings
from agent.evals import TrajectoryEvaluator
from agent.guardrails import (
    check_execution_rails,
    check_input_rails,
    check_output_rails,
)
from agent.llm_client import GeminiClient
from agent.memory import MemoryManager
from agent.models import (
    ExecutionTrace,
    PlanStep,
    RiskLevel,
    StepStatus,
    TaskGoal,
    ToolCallResult,
    WorkflowPlan,
    WorkflowStatus,
)
from agent.persistence import persistence
from agent.prompts import (
    FINAL_SUMMARY_PROMPT,
    PLANNING_PROMPT_TEMPLATE,
    SELF_CORRECTION_PROMPT,
)
from agent.security import audit_logger, requires_approval
from agent.task_graph import CyclicDependencyError, MissingDependencyError, TaskDAG
from agent.tools.registry import registry

logger = logging.getLogger("taskmaster.orchestrator")


class TaskmasterOrchestrator:
    def __init__(self):
        self.llm = GeminiClient()
        self.registry = registry
        self.memory = MemoryManager()
        self.evaluator = TrajectoryEvaluator(self.llm)
        self.workflows: Dict[str, WorkflowPlan] = {}
        self.traces: Dict[str, List[ExecutionTrace]] = {}
        self.event_callbacks: Dict[str, callable] = {}
        self._load_persisted_state()

    def _load_persisted_state(self):
        """Restore active or incomplete workflows from disk on startup."""
        for item in persistence.list_workflows():
            try:
                wf = WorkflowPlan(**item)
                self.workflows[wf.workflow_id] = wf
            except Exception as e:
                logger.warning(f"Could not load workflow {item.get('workflow_id')}: {e}")

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowPlan]:
        """Fetch workflow by ID from memory or disk persistence."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            data = persistence.load_workflow(workflow_id)
            if data:
                wf = WorkflowPlan(**data)
                self.workflows[workflow_id] = wf
        return wf

    def get_traces(self, workflow_id: str) -> List[ExecutionTrace]:
        """Fetch execution traces for a workflow."""
        return self.traces.get(workflow_id, [])

    def _add_trace(self, workflow_id: str, event_type: str, step_number: Optional[int] = None, details: Optional[Dict] = None):
        trace = ExecutionTrace(
            workflow_id=workflow_id,
            event_type=event_type,
            step_number=step_number,
            details=details or {},
            token_usage=self.llm.last_token_usage,
        )
        if workflow_id not in self.traces:
            self.traces[workflow_id] = []
        self.traces[workflow_id].append(trace)
        
        if workflow_id in self.event_callbacks:
            self.event_callbacks[workflow_id](trace)

        # Also log to security audit log
        audit_logger.log(
            event_type=event_type,
            workflow_id=workflow_id,
            step_number=step_number,
            details=details,
        )
        logger.info(f"[{workflow_id}] TRACE [{event_type}]: step={step_number} | {details}")

    def create_plan(self, goal_input: TaskGoal) -> WorkflowPlan:
        """
        Decomposes high-level goal into structured DAG workflow plan.
        Screens inputs through input rails and injects persistent memory context.
        """
        # 1. Input Guardrail check
        input_check = check_input_rails(goal_input.goal)
        if not input_check.passed:
            logger.warning(f"Input rail violation: {input_check.violations}")
            raise ValueError(f"Input rejected by safety rails: {', '.join(input_check.violations)}")

        # 2. Inject session memory context
        memory_context = self.memory.get_session_context()
        combined_context = {**goal_input.context, "persistent_memory": memory_context}

        tools_desc = self.registry.get_tools_description_prompt()
        prompt = PLANNING_PROMPT_TEMPLATE.format(
            goal=goal_input.goal,
            context=combined_context,
            tools_description=tools_desc,
        )

        llm_response = self.llm.generate_json(prompt, role="main")
        raw_steps = llm_response.get("steps", [])

        # Track token usage
        if self.llm.last_token_usage:
            goal_usage = self.llm.last_token_usage

        plan_steps = []
        for idx, step_dict in enumerate(raw_steps, start=1):
            depends = list(step_dict.get("depends_on", []))
            # Automatically infer dependencies from embedded or standalone step references (e.g. $step_1.id)
            args_str = json.dumps(step_dict.get("tool_args", {}))
            for ref_match in self.STEP_REF_PATTERN.finditer(args_str):
                ref_step_str = ref_match.group(1) or ref_match.group(3)
                if ref_step_str:
                    try:
                        ref_step_num = int(ref_step_str)
                        if 1 <= ref_step_num < idx and ref_step_num not in depends:
                            depends.append(ref_step_num)
                    except (ValueError, TypeError):
                        pass

            # Validate dependencies reference valid earlier steps
            valid_deps = sorted(list(set(d for d in depends if isinstance(d, int) and 1 <= d < idx)))

            plan_steps.append(
                PlanStep(
                    step_number=idx,
                    description=step_dict.get("description", f"Step {idx}"),
                    tool_name=step_dict.get("tool_name", "data_extractor"),
                    tool_args=step_dict.get("tool_args", {}),
                    reasoning=step_dict.get("reasoning", "Agent selected tool for step execution"),
                    status=StepStatus.PENDING,
                    depends_on=valid_deps,
                    complexity_score=step_dict.get("complexity_score", 3),
                )
            )

        workflow = WorkflowPlan(
            goal=goal_input.goal,
            steps=plan_steps,
            status=WorkflowStatus.CREATED,
            tags=goal_input.tags,
            require_approval=goal_input.require_approval,
        )

        if self.llm.last_token_usage:
            workflow.token_usage.add(self.llm.last_token_usage)

        self.workflows[workflow.workflow_id] = workflow
        persistence.save_workflow(workflow.workflow_id, workflow.model_dump(mode="json"))

        self._add_trace(
            workflow.workflow_id,
            "PLAN_GENERATED",
            details={
                "step_count": len(plan_steps),
                "steps": [s.description for s in plan_steps],
                "dag_dependencies": {s.step_number: s.depends_on for s in plan_steps},
            },
        )
        return workflow

    def execute_plan(self, workflow_id: str) -> WorkflowPlan:
        """Alias for execute_workflow."""
        return self.execute_workflow(workflow_id)

    def execute_workflow(self, workflow_id: str) -> WorkflowPlan:
        """
        Executes workflow steps respecting DAG dependencies.
        Steps within the same parallel group run concurrently.
        """
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            data = persistence.load_workflow(workflow_id)
            if data:
                workflow = WorkflowPlan(**data)
                self.workflows[workflow_id] = workflow
            else:
                raise ValueError(f"Workflow ID {workflow_id} not found.")

        workflow.status = WorkflowStatus.EXECUTING
        workflow.updated_at = datetime.now(timezone.utc)
        persistence.save_workflow(workflow_id, workflow.model_dump(mode="json"))

        # Build DAG and get parallel execution groups
        try:
            dag = TaskDAG(workflow.steps)
            parallel_groups = dag.get_parallel_groups()
        except CyclicDependencyError as e:
            logger.error(f"Cyclic dependency in workflow {workflow_id}: {e}")
            workflow.status = WorkflowStatus.FAILED
            workflow.summary = f"Workflow failed: Cyclic dependency detected — {e}"
            workflow.updated_at = datetime.now(timezone.utc)
            self._add_trace(workflow_id, "DAG_CYCLE_ERROR", details={"error": str(e)})
            persistence.save_workflow(workflow_id, workflow.model_dump(mode="json"))
            return workflow
        except MissingDependencyError as e:
            logger.error(f"Missing dependency in workflow {workflow_id}: {e}")
            workflow.status = WorkflowStatus.FAILED
            workflow.summary = f"Workflow failed: Missing dependency — {e}"
            workflow.updated_at = datetime.now(timezone.utc)
            self._add_trace(workflow_id, "DAG_MISSING_DEP_ERROR", details={"error": str(e)})
            persistence.save_workflow(workflow_id, workflow.model_dump(mode="json"))
            return workflow
        except Exception as e:
            logger.error(f"Unexpected error building DAG for workflow {workflow_id}: {e}")
            workflow.status = WorkflowStatus.FAILED
            workflow.summary = f"Workflow failed during DAG construction: {e}"
            workflow.updated_at = datetime.now(timezone.utc)
            self._add_trace(workflow_id, "DAG_BUILD_ERROR", details={"error": str(e)})
            persistence.save_workflow(workflow_id, workflow.model_dump(mode="json"))
            return workflow
        logger.info(f"Parallel execution groups for {workflow_id}: {parallel_groups}")

        step_map = {s.step_number: s for s in workflow.steps}
        completed_step_nums: Set[int] = {s.step_number for s in workflow.steps if s.status == StepStatus.COMPLETED}
        step_results: Dict[int, Any] = {s.step_number: s.result for s in workflow.steps if s.result is not None}

        for group in parallel_groups:
            # Filter to steps that still need execution
            pending_in_group = [sn for sn in group if step_map[sn].status != StepStatus.COMPLETED]
            if not pending_in_group:
                continue

            # Execute steps within a group concurrently
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(pending_in_group), 4)) as pool:
                futures = {}
                for step_num in pending_in_group:
                    step = step_map[step_num]

                    # Verify dependencies are met
                    if not all(dep in completed_step_nums for dep in step.depends_on):
                        logger.warning(f"Step {step_num} dependencies not satisfied: {step.depends_on}")
                        step.status = StepStatus.BLOCKED
                        continue

                    # Checkpoint
                    persistence.save_checkpoint(workflow_id, step_num, workflow.model_dump(mode="json"))
                    self._add_trace(workflow_id, "CHECKPOINT_SAVED", step_number=step_num)

                    # HITL gate — uses the workflow's configured approval mode (exempt if already approved)
                    if not getattr(step, "is_approved", False) and requires_approval(step.tool_name, approval_mode=workflow.require_approval):
                        step.status = StepStatus.WAITING_APPROVAL
                        workflow.status = WorkflowStatus.AWAITING_APPROVAL
                        workflow.paused_at_step = step_num
                        persistence.save_workflow(workflow_id, workflow.model_dump(mode="json"))
                        self._add_trace(workflow_id, "HITL_PAUSE", step_number=step_num, details={"tool": step.tool_name})
                        return workflow

                    # Execution guardrail — block on violation instead of continuing
                    exec_check = check_execution_rails(step.tool_name, step.tool_args)
                    if not exec_check.passed:
                        logger.warning(f"Execution rail violation for step {step_num}: {exec_check.violations}")
                        self._add_trace(workflow_id, "GUARDRAIL_BLOCK", step_number=step_num, details={"violations": exec_check.violations})
                        step.status = StepStatus.FAILED
                        step.error = f"Blocked by execution guardrail: {'; '.join(exec_check.violations)}"
                        continue

                    futures[pool.submit(self._execute_single_step, step, workflow, step_results)] = step_num

                for future in concurrent.futures.as_completed(futures):
                    step_num = futures[future]
                    step = step_map[step_num]
                    try:
                        result_data = future.result()
                        if step.status == StepStatus.COMPLETED:
                            completed_step_nums.add(step_num)
                            if step.result is not None:
                                step_results[step_num] = step.result
                    except Exception as e:
                        step.status = StepStatus.FAILED
                        step.error = str(e)
                        self._add_trace(workflow_id, "STEP_EXCEPTION", step_number=step_num, details={"error": str(e)})

        # Final summary synthesis
        accumulated_results = [s.result for s in workflow.steps if s.result is not None]
        # Count both FAILED and BLOCKED steps — blocked steps indicate unfulfilled dependencies
        failed_count = sum(1 for s in workflow.steps if s.status in (StepStatus.FAILED, StepStatus.BLOCKED))
        workflow.status = WorkflowStatus.COMPLETED if failed_count == 0 else WorkflowStatus.FAILED
        workflow.summary = self._synthesize_final_summary(workflow, accumulated_results)
        workflow.final_artifact = {"results": accumulated_results, "step_count": len(workflow.steps)}
        workflow.updated_at = datetime.now(timezone.utc)

        # Output guardrail — PII masking on final summary and intermediate results
        if workflow.summary:
            clean_summary, _ = check_output_rails(workflow.summary)
            workflow.summary = clean_summary
        if workflow.final_artifact and workflow.final_artifact.get("results"):
            from agent.security import mask_pii
            cleaned_results = []
            for r in workflow.final_artifact["results"]:
                cleaned_results.append(
                    json.loads(mask_pii(json.dumps(r, default=str)))
                    if isinstance(r, dict) else r
                )
            workflow.final_artifact["results"] = cleaned_results

        # Multi-dimensional Trajectory Evaluation
        eval_report = self.evaluator.evaluate_workflow(workflow)
        workflow.eval_scores = eval_report.model_dump(mode="json")

        # Reflect into Persistent Memory
        tools_used = [s.tool_name for s in workflow.steps]
        self.memory.reflect_on_workflow(
            workflow_id=workflow_id,
            goal=workflow.goal,
            steps_summary=workflow.summary or "",
            status=workflow.status.value,
            tools_used=tools_used,
        )

        persistence.save_workflow(workflow_id, workflow.model_dump(mode="json"))
        self._add_trace(
            workflow_id,
            "WORKFLOW_FINISHED",
            details={
                "status": workflow.status.value,
                "summary": workflow.summary,
                "overall_eval_score": eval_report.overall_score,
                "total_tokens": workflow.token_usage.total_tokens,
                "cost_usd": workflow.token_usage.total_estimated_cost_usd,
            },
        )
        self._add_trace(
            workflow_id,
            "COMPLETED",
            details={
                "status": workflow.status.value,
                "summary": workflow.summary,
                "overall_eval_score": eval_report.overall_score,
            },
        )
        return workflow

    def resume_workflow(self, workflow_id: str) -> WorkflowPlan:
        """Resume a paused workflow from its last checkpoint."""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            data = persistence.load_workflow(workflow_id)
            if not data:
                raise ValueError(f"Workflow {workflow_id} not found.")
            workflow = WorkflowPlan(**data)
            self.workflows[workflow_id] = workflow

        logger.info(f"Resuming workflow {workflow_id} from paused step {workflow.paused_at_step}")
        if workflow.paused_at_step:
            step = next((s for s in workflow.steps if s.step_number == workflow.paused_at_step), None)
            if step and step.status == StepStatus.WAITING_APPROVAL:
                step.is_approved = True
                step.status = StepStatus.PENDING
                self._add_trace(workflow_id, "HITL_APPROVED", step_number=step.step_number, details={"tool": step.tool_name})
            workflow.paused_at_step = None
        return self.execute_workflow(workflow_id)

    STEP_REF_PATTERN = re.compile(r'\$(?:\{step_(\d+)(?:\.([a-zA-Z0-9_]+))?\}|step_(\d+)(?:\.([a-zA-Z0-9_]+))?)')

    def _resolve_dynamic_args(self, args: Dict[str, Any], step_results: Dict[int, Any]) -> Dict[str, Any]:
        """Resolves references like $step_1.url or $step_2.id both as standalone values and embedded in strings."""
        import copy
        resolved = copy.deepcopy(args)

        def lookup_val(step_num_str: str, field: Optional[str]):
            try:
                step_num = int(step_num_str)
            except (ValueError, TypeError):
                return None
            res = step_results.get(step_num)
            if res is None:
                return None
            if field:
                if isinstance(res, dict):
                    return res.get(field)
                return getattr(res, field, None)
            return res

        def recurse_resolve(obj):
            if isinstance(obj, str):
                # 1. Check for exact full match (preserves complex types like dicts/lists)
                full_m = self.STEP_REF_PATTERN.fullmatch(obj)
                if full_m:
                    s_num = full_m.group(1) or full_m.group(3)
                    field = full_m.group(2) or full_m.group(4)
                    val = lookup_val(s_num, field)
                    return val if val is not None else obj

                # 2. Check for embedded references inside string (e.g. "https://$step_1.url/")
                def replace_match(match):
                    s_num = match.group(1) or match.group(3)
                    field = match.group(2) or match.group(4)
                    val = lookup_val(s_num, field)
                    if val is not None:
                        if isinstance(val, (dict, list)):
                            return json.dumps(val)
                        return str(val)
                    return match.group(0)

                return self.STEP_REF_PATTERN.sub(replace_match, obj)

            elif isinstance(obj, dict):
                return {k: recurse_resolve(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [recurse_resolve(v) for v in obj]
            return obj

        return recurse_resolve(resolved)

    # Errors worth retrying — transient network/timeout issues
    RETRYABLE_ERRORS = (TimeoutError, ConnectionError, OSError)
    MAX_RETRIES = 3

    def _execute_single_step(self, step: PlanStep, workflow: WorkflowPlan, step_results: Dict[int, Any]) -> None:
        """Execute a single step with retry/backoff for transient errors."""
        workflow_id = workflow.workflow_id
        resolved_args = self._resolve_dynamic_args(step.tool_args, step_results)

        step.status = StepStatus.IN_PROGRESS
        self._add_trace(workflow_id, "STEP_STARTED", step_number=step.step_number,
                        details={"tool": step.tool_name, "args": step.tool_args})

        tool = self.registry.get_tool(step.tool_name)
        if not tool:
            step.status = StepStatus.FAILED
            step.error = f"Tool '{step.tool_name}' not registered."
            self._add_trace(workflow_id, "TOOL_ERROR", step_number=step.step_number, details={"error": step.error})
            return

        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            start_time = time.time()
            try:
                result = tool.execute(resolved_args)
                elapsed_ms = (time.time() - start_time) * 1000
                step.execution_time_ms = elapsed_ms

                if result.success:
                    step.status = StepStatus.COMPLETED
                    step.result = result.data
                    self.memory.procedural.record_success(step.tool_name, resolved_args, workflow.goal)
                    self._add_trace(workflow_id, "TOOL_EXECUTION", step_number=step.step_number,
                                    details={"tool": step.tool_name, "result": result.data, "duration_ms": elapsed_ms})
                    return

                # Non-retryable tool failure — try self-correction once
                self.memory.procedural.record_failure(step.tool_name, resolved_args, result.error_message or "", workflow.goal)
                corrected = self._self_correct_step(step, resolved_args, result.error_message or "Unknown error", workflow)
                if corrected and corrected.success:
                    step.status = StepStatus.COMPLETED
                    step.result = corrected.data
                    self._add_trace(workflow_id, "SELF_CORRECTION", step_number=step.step_number,
                                    details={"status": "RECOVERED", "result": corrected.data})
                    return

                step.status = StepStatus.FAILED
                step.error = result.error_message
                self._add_trace(workflow_id, "SELF_CORRECTION", step_number=step.step_number,
                                details={"status": "FAILED_AFTER_CORRECTION", "error": result.error_message})
                return

            except self.RETRYABLE_ERRORS as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s
                    logger.warning(f"Step {step.step_number} transient error (attempt {attempt}/{self.MAX_RETRIES}), "
                                   f"retrying in {backoff}s: {e}")
                    time.sleep(backoff)
                    continue
                # Exhausted retries
                step.status = StepStatus.FAILED
                step.error = f"Failed after {self.MAX_RETRIES} retries: {e}"
                self._add_trace(workflow_id, "STEP_EXCEPTION", step_number=step.step_number,
                                details={"error": str(e), "retries_exhausted": True})
                return

            except Exception as e:
                # Non-retryable exception — fail immediately
                step.status = StepStatus.FAILED
                step.error = str(e)
                self._add_trace(workflow_id, "STEP_EXCEPTION", step_number=step.step_number, details={"error": str(e)})
                return

    def _self_correct_step(self, step: PlanStep, args: Dict, error: str, workflow: WorkflowPlan) -> Optional[ToolCallResult]:
        """Enhanced self-correction with alternative tool suggestion and retry."""
        # Definitive not-found / invalid resource error detection
        not_found_keywords = ["404", "not found", "does not exist", "invalid or missing", "not_found", "unresolved reference"]
        is_resource_not_found = any(kw in str(error).lower() for kw in not_found_keywords)

        tools_desc = self.registry.get_tools_description_prompt()
        prompt = SELF_CORRECTION_PROMPT.format(
            step_number=step.step_number,
            step_description=step.description,
            tool_name=step.tool_name,
            tool_args=json.dumps(args, indent=2, default=str),
            error_message=str(error),
            tools_description=tools_desc,
        )

        try:
            correction_res = self.llm.generate_json(prompt, role="fallback")
            if self.llm.last_token_usage:
                workflow.token_usage.add(self.llm.last_token_usage)

            suggested_tool = correction_res.get("suggested_tool", step.tool_name)
            corrected_args = correction_res.get("corrected_tool_args", args)

            # If resource is definitively not found, do not permit tool substitution
            if is_resource_not_found and suggested_tool != step.tool_name:
                logger.warning(
                    f"Self-correction rejected tool substitution from '{step.tool_name}' to '{suggested_tool}' "
                    f"on definitive resource-not-found error: {error}"
                )
                return None

            target_tool = self.registry.get_tool(suggested_tool)
            if target_tool:
                logger.info(f"Retrying with tool '{suggested_tool}' and args: {corrected_args}")
                return target_tool.execute(corrected_args)
        except Exception as e:
            logger.error(f"Self-correction failed: {e}")

        return None

    def _synthesize_final_summary(self, workflow: WorkflowPlan, results: List[Dict]) -> str:
        steps_summary = "\n".join(f"- Step {s.step_number}: {s.description} ({s.status.value})" for s in workflow.steps)
        artifacts_summary = json.dumps(results, indent=2, default=str)
        prompt = FINAL_SUMMARY_PROMPT.format(
            goal=workflow.goal,
            steps_summary=steps_summary,
            artifacts_summary=artifacts_summary,
        )
        failed_steps = [s for s in workflow.steps if s.status in (StepStatus.FAILED, StepStatus.BLOCKED)]
        completed_steps = [s for s in workflow.steps if s.status == StepStatus.COMPLETED]
        if failed_steps:
            honest_fallback = (
                f"## Workflow Execution: FAILED ({len(failed_steps)} steps failed)\n\n"
                f"**Goal**: {workflow.goal}\n\n"
                f"Completed {len(completed_steps)} of {len(workflow.steps)} steps. "
                f"Failed steps: {', '.join(f'Step {s.step_number}' for s in failed_steps)}."
            )
        else:
            honest_fallback = f"## Workflow Execution: COMPLETED\n\n**Goal**: {workflow.goal}\n\nAll {len(completed_steps)} steps executed successfully."

        try:
            res = self.llm.generate_json(prompt, role="main")
            if self.llm.last_token_usage:
                workflow.token_usage.add(self.llm.last_token_usage)
            return res.get("summary_markdown") or honest_fallback
        except Exception as e:
            logger.error(f"Summary synthesis failed: {e}")
            return honest_fallback


# Global singleton
orchestrator = TaskmasterOrchestrator()
