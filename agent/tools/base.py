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
            return ToolCallResult(
                tool_name=self.name,
                success=True,
                data=result_data,
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
