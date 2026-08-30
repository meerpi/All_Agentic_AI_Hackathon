"""
Agent2Agent (A2A) Standard Protocol — JSON-RPC 2.0 Server Handler.

Handles JSON-RPC 2.0 requests:
- `tasks/send`: Submit a new task or send input to a waiting task
- `tasks/get`: Retrieve current task state and artifacts
- `tasks/cancel`: Cancel an in-flight task
- `skills/list`: Discover available skills
"""

import json
import logging
from typing import Any, Dict, Optional
from agent.a2a.task_store import A2ATaskState, a2a_task_store
from agent.a2a.agent_card import get_agent_card

logger = logging.getLogger("taskmaster.a2a")


class A2AServer:
    """Implements JSON-RPC 2.0 handler for standard A2A requests."""

    def __init__(self, orchestrator=None, council=None):
        self.orchestrator = orchestrator
        self.council = council

    def handle_jsonrpc(self, request_data) -> Any:
        """Process incoming JSON-RPC 2.0 request or batch of requests."""
        # JSON-RPC 2.0 batch: request_data is a list of request objects
        if isinstance(request_data, list):
            if len(request_data) == 0:
                return self._error_response(None, -32600, "Invalid Request: batch is empty")
            return [self._handle_single_jsonrpc(req) for req in request_data]
        # Single request
        return self._handle_single_jsonrpc(request_data)

    def _handle_single_jsonrpc(self, request_data) -> Dict[str, Any]:
        """Process a single JSON-RPC 2.0 request object."""
        if not isinstance(request_data, dict):
            return self._error_response(None, -32600, "Invalid Request: each request must be a JSON object")

        req_id = request_data.get("id")
        method = request_data.get("method")
        params = request_data.get("params", {})

        if not method or request_data.get("jsonrpc") != "2.0":
            return self._error_response(req_id, -32600, "Invalid Request: must include 'jsonrpc': '2.0' and 'method'")

        try:
            if method == "skills/list":
                card = get_agent_card()
                return self._success_response(req_id, {"skills": card["skills"]})

            elif method == "tasks/send":
                return self._handle_tasks_send(req_id, params)

            elif method == "tasks/get":
                task_id = params.get("task_id")
                if not task_id:
                    return self._error_response(req_id, -32602, "Missing parameter 'task_id'")
                task = a2a_task_store.get_task(task_id)
                if not task:
                    return self._error_response(req_id, -32001, f"Task '{task_id}' not found")
                return self._success_response(req_id, task.model_dump(mode="json"))

            elif method == "tasks/cancel":
                task_id = params.get("task_id")
                if not task_id:
                    return self._error_response(req_id, -32602, "Missing parameter 'task_id'")
                success = a2a_task_store.cancel_task(task_id)
                return self._success_response(req_id, {"success": success, "task_id": task_id})

            else:
                return self._error_response(req_id, -32601, f"Method '{method}' not found")

        except Exception as e:
            logger.error(f"Error handling A2A JSON-RPC method {method}: {e}", exc_info=True)
            return self._error_response(req_id, -32603, f"Internal error: {str(e)}")

    def _handle_tasks_send(self, req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a task to internal engines."""
        skill_id = params.get("skill_id")
        task_params = params.get("parameters", {})

        if not skill_id:
            return self._error_response(req_id, -32602, "Missing parameter 'skill_id'")

        task = a2a_task_store.create_task(skill_id=skill_id, parameters=task_params)
        a2a_task_store.update_state(task.task_id, A2ATaskState.WORKING)

        try:
            # Delegate to orchestrator or council
            if skill_id == "workflow_planning" and self.orchestrator:
                from agent.models import TaskGoal
                goal = task_params.get("goal", "Execute task")
                require_approval = task_params.get("require_approval", False)
                tags = task_params.get("tags", [])
                
                task_goal = TaskGoal(goal=goal, require_approval=require_approval, tags=tags)
                plan = self.orchestrator.create_plan(task_goal)
                exec_plan = self.orchestrator.execute_plan(plan.workflow_id)
                
                a2a_task_store.add_artifact(task.task_id, "workflow_plan", exec_plan.model_dump(mode="json"))
                a2a_task_store.update_state(task.task_id, A2ATaskState.COMPLETED)

            elif skill_id == "council_dispatch" and self.council:
                brief = task_params.get("task_brief", "Council brief")
                result = self.council.dispatch(brief)
                a2a_task_store.add_artifact(task.task_id, "council_result", result)
                a2a_task_store.update_state(task.task_id, A2ATaskState.COMPLETED)

            elif skill_id == "prd_decomposition":
                from agent.prd_parser import PRDParser
                from agent.llm_client import GeminiClient
                from agent.tools.registry import registry
                parser = PRDParser(GeminiClient())
                parsed = parser.parse(task_params.get("prd_content", ""), registry.get_tools_description_prompt())
                a2a_task_store.add_artifact(task.task_id, "prd_tasks", parsed)
                a2a_task_store.update_state(task.task_id, A2ATaskState.COMPLETED)

            else:
                a2a_task_store.add_artifact(task.task_id, "result", {"status": "accepted", "skill": skill_id})
                a2a_task_store.update_state(task.task_id, A2ATaskState.COMPLETED)

        except Exception as e:
            logger.error(f"A2A task execution failed: {e}")
            a2a_task_store.update_state(task.task_id, A2ATaskState.FAILED, error=str(e))

        updated_task = a2a_task_store.get_task(task.task_id)
        return self._success_response(req_id, updated_task.model_dump(mode="json"))

    def _success_response(self, req_id: Any, result: Any) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "result": result, "id": req_id}

    def _error_response(self, req_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": req_id}
