"""
Task Expansion & Complexity Analysis Engine.

Provides:
- LLM-driven subtask decomposition (like `task-master expand --id=3 --num=5`)
- Fibonacci complexity scoring (1, 2, 3, 5, 8, 13, 21)
- Workflow-level complexity reports with bottleneck identification
"""

import logging
from typing import Any, Dict, List, Optional

from agent.models import ComplexityReport, PlanStep, StepStatus

logger = logging.getLogger("taskmaster.task_expansion")

FIBONACCI_SCORES = [1, 2, 3, 5, 8, 13, 21]

EXPANSION_PROMPT = """You are a senior technical project manager. Break down the following task into {num_subtasks} concrete, actionable subtasks.

Parent Task: "{description}"
Parent Reasoning: "{reasoning}"
Tool Context: {tool_name}

For each subtask, provide:
- description: What specifically needs to be done
- tool_name: Which tool to use (from the parent's tool context or suggest the most appropriate)
- tool_args: Concrete arguments for the tool
- reasoning: Why this subtask is needed
- depends_on_subtask: List of subtask numbers (1-indexed within this list) this depends on (empty if independent)

Return valid JSON:
{{
  "subtasks": [
    {{
      "subtask_number": 1,
      "description": "...",
      "tool_name": "...",
      "tool_args": {{}},
      "reasoning": "...",
      "depends_on_subtask": []
    }}
  ]
}}
"""

COMPLEXITY_PROMPT = """You are a senior engineering lead. Analyze the complexity of this task and assign a Fibonacci story point score.

Task: "{description}"
Tool: {tool_name}
Arguments: {tool_args}

Fibonacci scale:
- 1: Trivial (simple lookup, single API call, no logic)
- 2: Simple (straightforward action, minimal error handling)
- 3: Moderate (some business logic, 2-3 sub-operations)
- 5: Complex (significant logic, error handling, multiple integrations)
- 8: Very Complex (cross-system coordination, edge cases, validation)
- 13: Highly Complex (architectural decisions, multi-service orchestration)
- 21: Epic-level (should be decomposed into subtasks)

Return valid JSON:
{{
  "complexity_score": <fibonacci_number>,
  "reasoning": "Brief justification for the score",
  "should_expand": <true if score >= 13, else false>,
  "recommended_subtask_count": <number if should_expand, else 0>
}}
"""


class TaskExpansionEngine:
    """Handles subtask decomposition and complexity analysis."""

    def __init__(self, llm_client):
        self.llm = llm_client

    def expand_step(self, step: PlanStep, num_subtasks: int = 3,
                    available_tools: Optional[str] = None) -> List[PlanStep]:
        """
        Expand a single PlanStep into multiple subtasks via LLM.
        Returns list of new PlanStep objects.
        """
        prompt = EXPANSION_PROMPT.format(
            num_subtasks=num_subtasks,
            description=step.description,
            reasoning=step.reasoning,
            tool_name=step.tool_name,
        )

        try:
            result = self.llm.generate_json(prompt)
            raw_subtasks = result.get("subtasks", [])
        except Exception as e:
            logger.error(f"LLM expansion failed for step {step.step_number}: {e}")
            raw_subtasks = []

        if not raw_subtasks:
            # Fallback: generate simple sequential decomposition
            raw_subtasks = self._fallback_expansion(step, num_subtasks)

        subtasks = []
        base_number = step.step_number * 100  # e.g., step 3 → subtasks 301, 302, 303

        for idx, st in enumerate(raw_subtasks, start=1):
            # Map internal subtask deps to real step numbers
            internal_deps = st.get("depends_on_subtask", [])
            real_deps = [base_number + d for d in internal_deps if d < idx]

            subtask = PlanStep(
                step_number=base_number + idx,
                description=st.get("description", f"Subtask {idx} of step {step.step_number}"),
                tool_name=st.get("tool_name", step.tool_name),
                tool_args=st.get("tool_args", {}),
                reasoning=st.get("reasoning", f"Decomposed from parent step {step.step_number}"),
                status=StepStatus.PENDING,
                depends_on=real_deps,
                complexity_score=st.get("complexity_score"),
            )
            subtasks.append(subtask)

        step.subtasks = subtasks
        step.is_expanded = True
        logger.info(f"Expanded step {step.step_number} into {len(subtasks)} subtasks")
        return subtasks

    def score_complexity(self, step: PlanStep) -> PlanStep:
        """
        Assign a Fibonacci complexity score to a step via LLM.
        Modifies the step in place and returns it.
        """
        prompt = COMPLEXITY_PROMPT.format(
            description=step.description,
            tool_name=step.tool_name,
            tool_args=str(step.tool_args)[:500],
        )

        try:
            result = self.llm.generate_json(prompt)
            score = result.get("complexity_score", 3)
            # Snap to nearest valid Fibonacci number
            score = min(FIBONACCI_SCORES, key=lambda x: abs(x - score))
            step.complexity_score = score
            step.complexity_reasoning = result.get("reasoning", "")
        except Exception as e:
            logger.warning(f"Complexity scoring failed for step {step.step_number}: {e}")
            step.complexity_score = 3  # Default moderate
            step.complexity_reasoning = "Default score (LLM scoring unavailable)"

        return step

    def generate_complexity_report(self, steps: List[PlanStep],
                                   workflow_id: str = "") -> ComplexityReport:
        """
        Generate a comprehensive complexity report for all steps.
        Identifies bottlenecks and recommends expansion.
        """
        # Score any unscored steps
        for step in steps:
            if step.complexity_score is None:
                self.score_complexity(step)

        total_points = sum(s.complexity_score or 0 for s in steps)
        avg = total_points / len(steps) if steps else 0
        bottlenecks = [s.step_number for s in steps if (s.complexity_score or 0) >= 13]

        step_scores = []
        for s in steps:
            step_scores.append({
                "step_number": s.step_number,
                "description": s.description,
                "complexity_score": s.complexity_score,
                "reasoning": s.complexity_reasoning,
                "should_expand": (s.complexity_score or 0) >= 13,
                "tool": s.tool_name,
            })

        return ComplexityReport(
            workflow_id=workflow_id,
            total_steps=len(steps),
            total_complexity_points=total_points,
            avg_complexity=round(avg, 2),
            step_scores=step_scores,
            bottleneck_steps=bottlenecks,
        )

    def _fallback_expansion(self, step: PlanStep, num: int) -> List[Dict]:
        """Generate simple fallback subtasks when LLM is unavailable."""
        return [
            {
                "subtask_number": i,
                "description": f"Part {i}/{num} of: {step.description}",
                "tool_name": step.tool_name,
                "tool_args": step.tool_args,
                "reasoning": f"Sequential decomposition part {i}",
                "depends_on_subtask": [i - 1] if i > 1 else [],
            }
            for i in range(1, num + 1)
        ]
