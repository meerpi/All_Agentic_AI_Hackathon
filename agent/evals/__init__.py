"""
Agent Evaluation Framework — Trajectory-Based Multi-Dimensional Scorer.

Evaluates AI agent performance across 6 independent dimensions:
1. Plan Quality: Logical ordering, completeness, coverage of user goal
2. Plan Adherence: Fidelity to generated plan without hallucinated or skipped steps
3. Tool Selection Correctness: Right tool chosen for the task, no unnecessary tools
4. Argument Correctness: Valid parameters conforming to tool schemas
5. Error Recovery: Effective self-correction and pivoting when tools fail
6. Result Utilization: Tool output synthesized into final response vs internal hallucination
"""

import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("taskmaster.evals")


class EvaluationScore(BaseModel):
    score: float = Field(..., description="Score from 0.0 to 100.0")
    passed: bool = Field(..., description="Whether the score meets the minimum threshold (>= 75.0)")
    reasoning: str = Field(..., description="Detailed justification for the score")
    findings: List[str] = Field(default_factory=list)


class TrajectoryEvaluationReport(BaseModel):
    workflow_id: str
    overall_score: float = 0.0
    passed: bool = False
    plan_quality: EvaluationScore
    plan_adherence: EvaluationScore
    tool_selection: EvaluationScore
    argument_correctness: EvaluationScore
    error_recovery: EvaluationScore
    result_utilization: EvaluationScore
    execution_time_ms: float = 0.0
    total_steps: int = 0
    tools_used: List[str] = Field(default_factory=list)


EVAL_PROMPT = """You are an expert AI Agent Evaluation Judge. Analyze the complete execution trajectory of this workflow against the user's high-level goal.

High-Level Goal: "{goal}"

Plan Steps & Execution Trajectory:
{trajectory_json}

Final Artifact / Summary:
{final_summary}

Evaluate the agent strictly across these 6 dimensions (scores from 0 to 100):
1. plan_quality: Did the plan completely and logically address the goal?
2. plan_adherence: Did the agent execute the steps as planned without hallucinating or skipping?
3. tool_selection: Were the right tools chosen for each step without redundant tool calls?
4. argument_correctness: Were the tool arguments well-formed, complete, and correct?
5. error_recovery: If errors occurred, did the agent self-correct cleanly? (Score 100 if no errors occurred).
6. result_utilization: Did the final artifact/summary accurately incorporate the data returned by tools?

Return valid JSON with this exact schema:
{{
  "overall_score": 92.5,
  "plan_quality": {{ "score": 95.0, "reasoning": "...", "findings": ["..."] }},
  "plan_adherence": {{ "score": 90.0, "reasoning": "...", "findings": ["..."] }},
  "tool_selection": {{ "score": 95.0, "reasoning": "...", "findings": ["..."] }},
  "argument_correctness": {{ "score": 90.0, "reasoning": "...", "findings": ["..."] }},
  "error_recovery": {{ "score": 100.0, "reasoning": "...", "findings": ["..."] }},
  "result_utilization": {{ "score": 90.0, "reasoning": "...", "findings": ["..."] }}
}}
"""


class TrajectoryEvaluator:
    """Evaluates agent execution trajectories independently."""

    def __init__(self, llm_client=None):
        self.llm = llm_client

    def evaluate_workflow(self, workflow_plan) -> TrajectoryEvaluationReport:
        """Evaluate a completed WorkflowPlan object."""
        steps_data = []
        tools_used = []
        for step in workflow_plan.steps:
            tools_used.append(step.tool_name)
            steps_data.append({
                "step_number": step.step_number,
                "description": step.description,
                "tool_name": step.tool_name,
                "tool_args": step.tool_args,
                "status": step.status,
                "result": str(step.result)[:300] if step.result else None,
                "error": step.error,
                "depends_on": step.depends_on,
            })

        trajectory_json = json.dumps(steps_data, indent=2, default=str)
        final_summary = str(workflow_plan.final_artifact or workflow_plan.summary or "None")

        if self.llm:
            try:
                prompt = EVAL_PROMPT.format(
                    goal=workflow_plan.goal,
                    trajectory_json=trajectory_json,
                    final_summary=final_summary[:2000],
                )
                res = self.llm.generate_json(prompt)
                return self._parse_llm_eval(workflow_plan.workflow_id, res, len(steps_data), tools_used)
            except Exception as e:
                logger.error(f"LLM trajectory evaluation failed: {e}. Using deterministic rubric.")

        return self._deterministic_eval(workflow_plan, steps_data, tools_used)

    def _parse_llm_eval(self, workflow_id: str, res: Dict[str, Any], total_steps: int, tools_used: List[str]) -> TrajectoryEvaluationReport:
        def build_score(key: str) -> EvaluationScore:
            sub = res.get(key, {})
            score_val = float(sub.get("score", 80.0))
            return EvaluationScore(
                score=score_val,
                passed=score_val >= 75.0,
                reasoning=sub.get("reasoning", "LLM evaluated"),
                findings=sub.get("findings", []),
            )

        pq = build_score("plan_quality")
        pa = build_score("plan_adherence")
        ts = build_score("tool_selection")
        ac = build_score("argument_correctness")
        er = build_score("error_recovery")
        ru = build_score("result_utilization")

        overall = float(res.get("overall_score", (pq.score + pa.score + ts.score + ac.score + er.score + ru.score) / 6.0))

        return TrajectoryEvaluationReport(
            workflow_id=workflow_id,
            overall_score=round(overall, 1),
            passed=overall >= 75.0,
            plan_quality=pq,
            plan_adherence=pa,
            tool_selection=ts,
            argument_correctness=ac,
            error_recovery=er,
            result_utilization=ru,
            total_steps=total_steps,
            tools_used=tools_used,
        )

    def _deterministic_eval(self, workflow_plan, steps_data: List[Dict], tools_used: List[str]) -> TrajectoryEvaluationReport:
        """Deterministic fallback rubric based on execution facts."""
        completed_steps = [s for s in workflow_plan.steps if s.status.value == "COMPLETED"]
        failed_steps = [s for s in workflow_plan.steps if s.status.value == "FAILED"]
        total = len(workflow_plan.steps) or 1

        adherence_score = (len(completed_steps) / total) * 100.0
        plan_quality_score = 90.0 if total >= 2 else 70.0
        tool_selection_score = 95.0 if len(set(tools_used)) >= 1 else 60.0
        arg_score = 90.0 if not any("error" in s and s["error"] for s in steps_data) else 70.0
        err_score = 100.0 if len(failed_steps) == 0 else 60.0
        util_score = 90.0 if workflow_plan.final_artifact else 70.0

        overall = (adherence_score + plan_quality_score + tool_selection_score + arg_score + err_score + util_score) / 6.0

        return TrajectoryEvaluationReport(
            workflow_id=workflow_plan.workflow_id,
            overall_score=round(overall, 1),
            passed=overall >= 75.0,
            plan_quality=EvaluationScore(score=plan_quality_score, passed=plan_quality_score >= 75.0, reasoning="Deterministic structure check"),
            plan_adherence=EvaluationScore(score=adherence_score, passed=adherence_score >= 75.0, reasoning=f"{len(completed_steps)}/{total} steps completed"),
            tool_selection=EvaluationScore(score=tool_selection_score, passed=tool_selection_score >= 75.0, reasoning=f"Used tools: {list(set(tools_used))}"),
            argument_correctness=EvaluationScore(score=arg_score, passed=arg_score >= 75.0, reasoning="Schema conformity check"),
            error_recovery=EvaluationScore(score=err_score, passed=err_score >= 75.0, reasoning=f"{len(failed_steps)} failures encountered"),
            result_utilization=EvaluationScore(score=util_score, passed=util_score >= 75.0, reasoning="Artifact generation check"),
            total_steps=len(workflow_plan.steps),
            tools_used=tools_used,
        )
