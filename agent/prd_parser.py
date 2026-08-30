"""
PRD (Product Requirements Document) Parser.

Parses unstructured .txt/.md requirements documents into structured
task graphs with dependencies, priorities, and acceptance criteria —
analogous to `task-master parse-prd`.
"""

import logging
from typing import Any, Dict, List, Optional

from agent.models import PlanStep, RiskLevel, StepStatus

logger = logging.getLogger("taskmaster.prd_parser")

PRD_PARSING_PROMPT = """You are a senior technical product manager. Parse the following Product Requirements Document (PRD) into a structured, dependency-ordered set of actionable tasks.

## PRD Content:
\"\"\"
{prd_content}
\"\"\"

## Available Tools:
{tools_description}

## Instructions:
1. Extract concrete, actionable tasks from the requirements.
2. For each task, identify which tool(s) can execute it.
3. Define dependencies between tasks (which tasks must complete before others can start).
4. Assign a priority (1=highest, 5=lowest).
5. Write clear acceptance criteria for each task.
6. Assign a Fibonacci complexity score (1,2,3,5,8,13,21).

Return valid JSON with this schema:
{{
  "project_title": "Short project title",
  "total_tasks": <number>,
  "tasks": [
    {{
      "task_number": 1,
      "description": "Clear, actionable task description",
      "tool_name": "exact_tool_name",
      "tool_args": {{}},
      "reasoning": "Why this task is needed and why this tool was chosen",
      "depends_on": [],
      "priority": 1,
      "complexity_score": 3,
      "acceptance_criteria": ["Criterion 1", "Criterion 2"],
      "risk_level": "LOW"
    }}
  ]
}}

IMPORTANT:
- Dependencies must reference valid task_numbers (no circular dependencies).
- Use ONLY tools from the available tools list.
- Order tasks logically: infrastructure before features, data before UI.
"""


class PRDParser:
    """Parses PRD documents into structured task graphs."""

    def __init__(self, llm_client):
        self.llm = llm_client

    def parse(self, prd_content: str, tools_description: str = "") -> Dict[str, Any]:
        """
        Parse a PRD text into a structured task graph.

        Args:
            prd_content: Raw PRD text (.txt or .md content)
            tools_description: Description of available tools

        Returns:
            Dict with 'project_title', 'tasks' (List[PlanStep]), 'metadata'
        """
        if not prd_content or not prd_content.strip():
            return {
                "project_title": "Empty PRD",
                "tasks": [],
                "metadata": {"error": "PRD content is empty"},
            }

        prompt = PRD_PARSING_PROMPT.format(
            prd_content=prd_content[:8000],  # Cap to prevent context overflow
            tools_description=tools_description or "No specific tools provided — use general tool names.",
        )

        try:
            result = self.llm.generate_json(prompt)
        except Exception as e:
            logger.error(f"LLM PRD parsing failed: {e}")
            result = self._fallback_parse(prd_content)

        raw_tasks = result.get("tasks", [])
        plan_steps = []

        for task in raw_tasks:
            risk_str = task.get("risk_level", "LOW").upper()
            try:
                risk = RiskLevel(risk_str)
            except ValueError:
                risk = RiskLevel.LOW

            step = PlanStep(
                step_number=task.get("task_number", len(plan_steps) + 1),
                description=task.get("description", "Parsed task"),
                tool_name=task.get("tool_name", "data_extractor"),
                tool_args=task.get("tool_args", {}),
                reasoning=task.get("reasoning", "Extracted from PRD"),
                status=StepStatus.PENDING,
                depends_on=task.get("depends_on", []),
                complexity_score=task.get("complexity_score"),
                complexity_reasoning=task.get("acceptance_criteria", [""])[0] if task.get("acceptance_criteria") else None,
                risk_level=risk,
            )
            plan_steps.append(step)

        return {
            "project_title": result.get("project_title", "Parsed PRD Project"),
            "tasks": plan_steps,
            "metadata": {
                "total_tasks": len(plan_steps),
                "total_complexity_points": sum(s.complexity_score or 0 for s in plan_steps),
                "dependency_edges": sum(len(s.depends_on) for s in plan_steps),
            },
        }

    def parse_file(self, file_path: str, tools_description: str = "") -> Dict[str, Any]:
        """Parse a PRD from a file path (.txt or .md)."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return self.parse(content, tools_description)
        except FileNotFoundError:
            return {
                "project_title": "File Not Found",
                "tasks": [],
                "metadata": {"error": f"File not found: {file_path}"},
            }
        except Exception as e:
            return {
                "project_title": "Parse Error",
                "tasks": [],
                "metadata": {"error": str(e)},
            }

    def _fallback_parse(self, prd_content: str) -> Dict[str, Any]:
        """Simple heuristic fallback when LLM is unavailable."""
        lines = [l.strip() for l in prd_content.split("\n") if l.strip()]
        tasks = []
        task_num = 0

        for line in lines:
            # Look for bullet points, numbered items, or requirement-like sentences
            if any(line.startswith(p) for p in ("- ", "* ", "• ")) or \
               (len(line) > 2 and line[0].isdigit() and line[1] in ".)" ):
                task_num += 1
                clean = line.lstrip("-*•0123456789.) ").strip()
                tasks.append({
                    "task_number": task_num,
                    "description": clean,
                    "tool_name": "data_extractor",
                    "tool_args": {"input": clean},
                    "reasoning": "Extracted from PRD bullet point",
                    "depends_on": [task_num - 1] if task_num > 1 else [],
                    "priority": 3,
                    "complexity_score": 3,
                    "acceptance_criteria": [f"'{clean}' is completed"],
                    "risk_level": "LOW",
                })

        return {
            "project_title": lines[0][:100] if lines else "Parsed PRD",
            "total_tasks": len(tasks),
            "tasks": tasks,
        }
