import pkgutil
import importlib
import inspect
import agent.tools
from typing import Dict, List, Optional, Type
from agent.tools.base import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        for _, module_name, _ in pkgutil.iter_modules(agent.tools.__path__):
            if module_name in ["base", "registry"]:
                continue
            module = importlib.import_module(f"agent.tools.{module_name}")
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, BaseTool) and obj is not BaseTool:
                    # Prevent abstract classes or base classes from being registered
                    if not inspect.isabstract(obj):
                        try:
                            self.register(obj())
                        except Exception as e:
                            print(f"Failed to load tool {name}: {e}")

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, str]]:
        return [{"name": tool.name, "description": tool.description} for tool in self._tools.values()]

    def get_tools_description_prompt(self) -> str:
        lines = []
        for tool in self._tools.values():
            lines.append(f"- **{tool.name}**: {tool.description}")
        return "\n".join(lines)


# Global registry singleton
registry = ToolRegistry()
