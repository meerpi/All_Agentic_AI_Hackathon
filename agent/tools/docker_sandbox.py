import subprocess
import tempfile
import os
from typing import Any, Dict
from agent.tools.base import BaseTool

class DockerSandboxTool(BaseTool):
    name = "docker_sandbox"
    description = "Safely executes untrusted Python code inside an isolated Docker container."

    def run(self, code: str, image: str = "python:3.10-slim", timeout_seconds: int = 15, **kwargs: Any) -> Dict[str, Any]:
        """Runs the provided python code in a temporary docker container."""
        # Create a temporary file to hold the code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tf:
            tf.write(code)
            temp_path = tf.name

        try:
            # Mount the temp file into the container and execute it
            cmd = [
                "docker", "run", "--rm",
                "--network", "none", # Sandbox networking
                "-v", f"{temp_path}:/app/script.py:ro",
                image,
                "python", "/app/script.py"
            ]
            
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
                "error": f"Execution timed out after {timeout_seconds} seconds."
            }
        except Exception as e:
            # Fallback if Docker is not installed or daemon is not running
            return {
                "status": "FAILED",
                "error": f"Failed to execute sandbox: {str(e)}. Is Docker running?"
            }
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
