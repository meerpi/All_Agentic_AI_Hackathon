"""
Task & Schedule Manager Tool for Taskmaster and Strands Agents SDK.

Provides native capabilities for:
- Creating, tracking, and updating operational tasks with priorities and dependencies
- Setting up recurring background schedules and automated execution intervals
- Querying active task boards and pending scheduled jobs
"""

import logging
from typing import Any, Dict, List, Optional

from agent.database import db
from agent.tools.base import BaseTool

logger = logging.getLogger("taskmaster.tools.task_scheduler")


class TaskSchedulerTool(BaseTool):
    name = "task_scheduler"
    description = (
        "Operational Task & Schedule Manager. Allows the agent to create real tracked tasks "
        "(with priority, dependencies, due dates), query task boards, update task lifecycle status, "
        "and register automated background schedules (with recurring intervals in minutes or cron). "
        "Actions: create_task, list_tasks, update_task_status, create_schedule, list_schedules, trigger_schedule."
    )

    def run(
        self,
        action: str = "list_tasks",
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: str = "MEDIUM",
        assigned_to: Optional[str] = None,
        due_date: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        task_id: Optional[str] = None,
        status: Optional[str] = None,
        name: Optional[str] = None,
        goal: Optional[str] = None,
        interval_minutes: int = 60,
        cron_expression: Optional[str] = None,
        schedule_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        act = (action or "list_tasks").lower().strip()

        try:
            if act == "create_task":
                if not title:
                    return {"status": "FAILED", "error": "Action 'create_task' requires 'title' parameter."}
                task = db.create_task(
                    title=title,
                    description=description or "",
                    priority=priority,
                    assigned_to=assigned_to,
                    due_date=due_date,
                    dependencies=dependencies,
                    task_id=task_id,
                )
                return {
                    "status": "SUCCESS",
                    "action": "create_task",
                    "task": task,
                    "message": f"Task '{task['title']}' created successfully with ID {task['id']} [Priority: {task['priority']}].",
                }

            elif act == "list_tasks":
                tasks = db.list_tasks(status=status)
                return {
                    "status": "SUCCESS",
                    "action": "list_tasks",
                    "total_tasks": len(tasks),
                    "tasks": tasks,
                }

            elif act == "update_task_status":
                if not task_id or not status:
                    return {"status": "FAILED", "error": "Action 'update_task_status' requires 'task_id' and 'status'."}
                updated = db.update_task_status(task_id, status)
                if not updated:
                    return {"status": "FAILED", "error": f"Task {task_id} not found."}
                return {
                    "status": "SUCCESS",
                    "action": "update_task_status",
                    "task": updated,
                    "message": f"Task {task_id} status updated to {status.upper()}.",
                }

            elif act == "create_schedule":
                sched_name = name or title or "Automated Workflow Schedule"
                sched_goal = goal or description or "Run operational health check"
                schedule = db.create_schedule(
                    name=sched_name,
                    goal=sched_goal,
                    interval_minutes=interval_minutes,
                    cron_expression=cron_expression,
                    schedule_id=schedule_id,
                )
                return {
                    "status": "SUCCESS",
                    "action": "create_schedule",
                    "schedule": schedule,
                    "message": f"Schedule '{sched_name}' registered with ID {schedule['id']}. Recurring every {interval_minutes} minutes.",
                }

            elif act == "list_schedules":
                schedules = db.list_schedules(status=status)
                return {
                    "status": "SUCCESS",
                    "action": "list_schedules",
                    "total_schedules": len(schedules),
                    "schedules": schedules,
                }

            elif act == "trigger_schedule":
                if not schedule_id:
                    return {"status": "FAILED", "error": "Action 'trigger_schedule' requires 'schedule_id'."}
                schedules = db.list_schedules()
                target = next((s for s in schedules if s["id"] == schedule_id), None)
                if not target:
                    return {"status": "FAILED", "error": f"Schedule {schedule_id} not found."}
                
                # Immediate execution of target schedule goal
                from agent.strands_bridge import TaskmasterProAgent
                agent = TaskmasterProAgent(enable_hitl=False, workflow_id=f"scheduled-{schedule_id}")
                exec_res = agent.run(target["goal"])
                return {
                    "status": "SUCCESS",
                    "action": "trigger_schedule",
                    "schedule_id": schedule_id,
                    "execution_status": exec_res.get("status"),
                    "output_preview": exec_res.get("output", "")[:400],
                }

            else:
                return {
                    "status": "FAILED",
                    "error": f"Unknown action '{act}'. Supported: create_task, list_tasks, update_task_status, create_schedule, list_schedules, trigger_schedule",
                }

        except Exception as e:
            logger.error(f"Error in TaskSchedulerTool: {e}", exc_info=True)
            return {"status": "FAILED", "error": str(e)}
