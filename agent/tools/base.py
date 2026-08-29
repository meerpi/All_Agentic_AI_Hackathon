import time
from abc import ABC, abstractmethod
from typing import Any, Dict
from agent.models import ToolCallResult


class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, **kwargs: Any) -> Dict[str, Any]:
        """Execute tool logic and return result dictionary."""
        pass

    def execute(self, **kwargs: Any) -> ToolCallResult:
        """Wrapper around run method that measures execution time and catches exceptions."""
        start_time = time.time()
        try:
            result_data = self.run(**kwargs)
            duration = (time.time() - start_time) * 1000
            
            success = True
            error_message = None
            if isinstance(result_data, dict) and result_data.get("status") == "FAILED":
                success = False
                error_message = result_data.get("error", "Unknown tool error")
            
            return ToolCallResult(
                tool_name=self.name,
                success=success,
                data=result_data,
                error_message=error_message,
                execution_time_ms=round(duration, 2)
            )
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return ToolCallResult(
                tool_name=self.name,
                success=False,
                data={},
                error_message=str(e),
                execution_time_ms=round(duration, 2)
            )
