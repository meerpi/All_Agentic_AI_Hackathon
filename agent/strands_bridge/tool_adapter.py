"""
Tool Adapter bridging Taskmaster's BaseTool registry to Strands Agents SDK.

Converts any Taskmaster BaseTool subclass into a first-class Strands `@tool`
with preserved docstrings, JSON schema input validation, and execution timing.
"""

import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, Set

from strands.tools.decorator import tool

from agent.tools.base import BaseTool
from agent.tools.registry import registry

logger = logging.getLogger("taskmaster.strands_bridge.tools")

# Sensitive tools requiring explicit human approval before execution
SENSITIVE_TOOLS: Set[str] = {
    "github",
    "jira",
    "gmail",
    "slack",
    "action_dispatcher",
    "docker_sandbox",
    "python_sandbox",
    "os_desktop",
    "os_desktop_tool",
}

# Read-only or idempotent tools that can run automatically
SAFE_TOOLS: Set[str] = {
    "data_extractor",
    "validator",
    "db_manager",
    "report_generator",
    "google_docs",
    "google_sheets",
    "google_calendar",
    "task_scheduler",
    "media_controller",
}


def adapt_basetool_to_strands(base_tool: BaseTool) -> Any:
    """
    Wrap a Taskmaster BaseTool instance into a native Strands tool.
    Uses base_tool.run signature, docstrings, and parameter types.
    """
    run_func = base_tool.run

    def wrapped_tool(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Wrapper invoking base_tool.execute() and returning the result payload."""
        try:
            # Unpack nested kwargs if the LLM passed kwargs as a dict or JSON string
            clean_kwargs = dict(kwargs)
            if "kwargs" in clean_kwargs:
                nested = clean_kwargs.pop("kwargs")
                if isinstance(nested, dict):
                    clean_kwargs.update(nested)
                elif isinstance(nested, str):
                    try:
                        import json
                        parsed = json.loads(nested)
                        if isinstance(parsed, dict):
                            clean_kwargs.update(parsed)
                    except Exception:
                        pass

            res = base_tool.execute(tool_args=clean_kwargs)
            if res.success:
                return res.data if isinstance(res.data, dict) else {"result": res.data}
            return {
                "status": "FAILED",
                "error": res.error_message or "Execution failed without explicit error",
                "data": res.data,
            }
        except Exception as e:
            logger.error(f"Error executing Strands tool {base_tool.name}: {e}", exc_info=True)
            return {"status": "FAILED", "error": str(e)}

    # Retain the run signature, excluding **kwargs so Pydantic schema doesn't demand 'kwargs'
    sig = inspect.signature(run_func)
    clean_params = [
        p for p in sig.parameters.values()
        if p.kind != inspect.Parameter.VAR_KEYWORD and p.name != "kwargs"
    ]
    wrapped_tool.__signature__ = sig.replace(parameters=clean_params)
    wrapped_tool.__annotations__ = {k: v for k, v in getattr(run_func, "__annotations__", {}).items() if k != "kwargs"}
    wrapped_tool.__doc__ = base_tool.description or run_func.__doc__ or f"Execute {base_tool.name}"
    wrapped_tool.__name__ = base_tool.name

    # Create Strands DecoratedFunctionTool with explicit name and description
    strands_tool = tool(
        wrapped_tool,
        name=base_tool.name,
        description=base_tool.description,
    )
    return strands_tool


class StrandsToolRegistry:
    """Registry managing adapted Strands tools for Taskmaster."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._refresh()

    def _refresh(self):
        """Convert all registered BaseTools into Strands tools."""
        for tool_name, tool_inst in registry._tools.items():
            try:
                self._cache[tool_name] = adapt_basetool_to_strands(tool_inst)
            except Exception as e:
                logger.warning(f"Could not adapt tool {tool_name} to Strands: {e}")

    def get_tool(self, name: str) -> Optional[Any]:
        if name not in self._cache:
            base_t = registry.get_tool(name)
            if base_t:
                self._cache[name] = adapt_basetool_to_strands(base_t)
        return self._cache.get(name)

    def get_tools(self, names: Optional[List[str]] = None) -> List[Any]:
        """Return list of Strands tools, optionally filtered by names."""
        if names:
            return [self.get_tool(n) for n in names if self.get_tool(n) is not None]
        return list(self._cache.values())

    def get_professional_tools(self) -> List[Any]:
        """
        Return the curated tool suite for Track 2 (Professional Agents):
        PRD & Spec parsing, Jira & GitHub management, Docker smoke tests,
        Slack & Gmail communication, DB persistence, validation, and briefings.
        """
        preferred_names = [
            "task_scheduler",
            "jira",
            "github",
            "docker_sandbox",
            "python_sandbox",
            "slack",
            "gmail",
            "google_docs",
            "google_sheets",
            "google_calendar",
            "data_extractor",
            "db_manager",
            "validator",
            "report_generator",
            "browser_controller",
            "memory_tool",
            "os_desktop_tool",
            "media_controller",
        ]
        tools = []
        for name in preferred_names:
            t = self.get_tool(name)
            if t is not None:
                tools.append(t)
        return tools

    def get_safe_tool_names(self) -> List[str]:
        """Return names of tools that do not require human-in-the-loop approval."""
        return [name for name in self._cache.keys() if name not in SENSITIVE_TOOLS]

    def get_sensitive_tool_names(self) -> List[str]:
        """Return names of tools that trigger HITL approval interrupts."""
        return [name for name in self._cache.keys() if name in SENSITIVE_TOOLS]


# Global singleton instance
strands_tool_registry = StrandsToolRegistry()
