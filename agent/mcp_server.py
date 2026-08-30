"""
Model Context Protocol (MCP) Server for Taskmaster.

Exposes Taskmaster tools and capabilities directly over MCP so that
external coding agents (Claude Code, Cursor, Windsurf) can connect
without separate API keys using `mcp.json` or `claude_desktop_config.json`.

Tools exposed:
- run_workflow: Plan and execute an autonomous workflow
- parse_prd: Parse PRD text into structured DAG tasks
- expand_task: Decompose a task into subtasks
- analyze_complexity: Get Fibonacci complexity scores
- search_memory: Query cross-session episodic & semantic memory
- get_jira_sprint: Fetch sprint issues and status
"""

import asyncio
import json
import sys
from typing import Any, Dict, List, Optional


def build_mcp_tools_manifest() -> List[Dict[str, Any]]:
    """Return JSON schema tool declarations for MCP clients."""
    return [
        {
            "name": "run_workflow",
            "description": "Plan and autonomously execute a multi-step taskmaster workflow (e.g. create Jira issues, send emails, sync sheets).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "High-level objective"},
                    "require_approval": {"type": "boolean", "default": False},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["goal"],
            },
        },
        {
            "name": "parse_prd",
            "description": "Parse a Product Requirements Document (PRD) into a structured DAG of tasks with dependencies and complexity scores.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prd_content": {"type": "string", "description": "Raw text or markdown PRD"},
                },
                "required": ["prd_content"],
            },
        },
        {
            "name": "expand_task",
            "description": "Decompose a single task into detailed subtasks with dependency ordering.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Task description"},
                    "num_subtasks": {"type": "integer", "default": 3},
                    "tool_name": {"type": "string", "default": "data_extractor"},
                },
                "required": ["description"],
            },
        },
        {
            "name": "search_memory",
            "description": "Search cross-session episodic, semantic, and procedural memory.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword search query"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_jira_issues",
            "description": "Fetch current issues from the live Jira Cloud backlog.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
    ]


def handle_mcp_call(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an MCP tool call."""
    if tool_name == "run_workflow":
        from agent.orchestrator import orchestrator
        from agent.models import TaskGoal
        goal = TaskGoal(
            goal=arguments.get("goal", ""),
            require_approval=arguments.get("require_approval", False),
            tags=arguments.get("tags", []),
        )
        plan = orchestrator.create_plan(goal)
        exec_plan = orchestrator.execute_plan(plan.workflow_id)
        return {"workflow_id": exec_plan.workflow_id, "status": exec_plan.status.value, "summary": exec_plan.summary}

    elif tool_name == "parse_prd":
        from agent.prd_parser import PRDParser
        from agent.llm_client import GeminiClient
        from agent.tools.registry import registry
        parser = PRDParser(GeminiClient())
        result = parser.parse(arguments.get("prd_content", ""), registry.get_tools_description_prompt())
        return result

    elif tool_name == "expand_task":
        from agent.task_expansion import TaskExpansionEngine
        from agent.llm_client import GeminiClient
        from agent.models import PlanStep
        engine = TaskExpansionEngine(GeminiClient())
        step = PlanStep(
            step_number=1,
            description=arguments.get("description", ""),
            tool_name=arguments.get("tool_name", "data_extractor"),
            reasoning="MCP expand request",
        )
        subtasks = engine.expand_step(step, num_subtasks=arguments.get("num_subtasks", 3))
        return {"subtasks": [s.model_dump(mode="json") for s in subtasks]}

    elif tool_name == "search_memory":
        from agent.memory import MemoryManager
        mem = MemoryManager()
        return mem.search_all(arguments.get("query", ""))

    elif tool_name == "get_jira_issues":
        from agent.tools.jira_tool import JiraTool
        jt = JiraTool()
        res = jt.execute(action="list_issues", project_key=arguments.get("project_key"))
        return res.data if res.success else {"error": res.error_message}

    raise ValueError(f"Unknown MCP tool: {tool_name}")


async def stdio_mcp_loop():
    """Simple JSON-RPC stdio loop for standard MCP clients."""
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            req = json.loads(line.decode().strip())
            req_id = req.get("id")
            method = req.get("method")

            if method == "tools/list":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": build_mcp_tools_manifest()}}
            elif method == "tools/call":
                params = req.get("params", {})
                tool_res = handle_mcp_call(params.get("name"), params.get("arguments", {}))
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(tool_res)}]}}
            else:
                resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method {method} not supported"}}

            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(stdio_mcp_loop())
