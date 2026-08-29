from typing import Dict, List, Optional, Type
from agent.tools.base import BaseTool
from agent.tools.data_extractor import DataExtractorTool
from agent.tools.db_manager import DBManagerTool
from agent.tools.action_dispatcher import ActionDispatcherTool
from agent.tools.report_generator import ReportGeneratorTool
from agent.tools.validator import ValidatorTool


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        defaults = [
            DataExtractorTool(),
            DBManagerTool(),
            ActionDispatcherTool(),
            ReportGeneratorTool(),
            ValidatorTool()
        ]
        for tool in defaults:
            self.register(tool)

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
