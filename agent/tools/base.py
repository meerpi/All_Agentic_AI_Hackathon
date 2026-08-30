import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from agent.models import ToolCallResult


class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, **kwargs: Any) -> Dict[str, Any]:
        """Execute tool logic and return result dictionary."""
        pass

    def execute(self, tool_args: Optional[Dict[str, Any]] = None, **kwargs: Any) -> ToolCallResult:
        """
        Wrapper around run method that measures execution time and catches exceptions.
        Accepts arguments as a single dictionary `tool_args` or keyword arguments `**kwargs`.
        """
        start_time = time.time()
        args = dict(tool_args or {})
        args.update(kwargs)

        try:
            result_data = self.run(**args)
            duration = (time.time() - start_time) * 1000

            success = True
            error_message = None
            if isinstance(result_data, dict):
                if result_data.get("status") == "FAILED" or "error" in result_data:
                    success = False
                    error_message = result_data.get("error", "Unknown tool error")

            return ToolCallResult(
                tool_name=self.name,
                success=success,
                data=result_data if isinstance(result_data, dict) else {"result": result_data},
                error_message=error_message,
                execution_time_ms=round(duration, 2),
            )
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ToolCallResult(
                tool_name=self.name,
                success=False,
                data={},
                error_message=str(e),
                execution_time_ms=round(duration, 2),
            )
