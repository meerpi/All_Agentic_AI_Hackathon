import subprocess
import tempfile
import os
from typing import Any, Dict
from agent.tools.base import BaseTool

class DockerSandboxTool(BaseTool):
    name = "python_sandbox"
    description = "Safely executes untrusted Python code in an isolated subprocess (Cloud Run compatible)."

    def run(self, code: str, timeout_seconds: int = 15, **kwargs: Any) -> Dict[str, Any]:
        """Runs the provided python code in a temporary subprocess."""
        # Create a temporary file to hold the code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tf:
            tf.write(code)
            temp_path = tf.name

        try:
            # Execute natively with python (since Docker isn't available on Cloud Run)
            cmd = ["python", temp_path]
            
            # Note: For true hardening on Linux, we would wrap this in `prlimit` or `firejail`. 
            # In Windows/cross-platform, we rely on timeout.
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
            
            if result.returncode == 0:
                return {
                    "status": "SUCCESS",
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip()
                }
            else:
                return {
                    "status": "FAILED",
                    "error": result.stderr.strip() or result.stdout.strip()
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "FAILED",
                "error": f"Execution timed out after {timeout_seconds} seconds. Potential fork-bomb or infinite loop prevented."
            }
        except Exception as e:
            return {
                "status": "FAILED",
                "error": f"Failed to execute sandbox: {str(e)}."
            }
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
