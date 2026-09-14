import subprocess
import sys
import tempfile
import os
from typing import Any, Dict
from agent.tools.base import BaseTool

class DockerSandboxTool(BaseTool):
    name = "python_sandbox"
    description = "Executes untrusted Python code in a subprocess (isolated by timeout, sandboxed from host secrets - not a full execution sandbox)."

    def run(self, code: str, timeout_seconds: int = 15, **kwargs: Any) -> Dict[str, Any]:
        """Runs the provided python code in a temporary subprocess."""
        # Create a temporary file to hold the code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tf:
            tf.write(code)
            temp_path = tf.name

        try:
            # Execute natively with active Python runtime
            cmd = [sys.executable, temp_path]
            
            # Note: For true hardening on Linux, we would wrap this in `prlimit` or `firejail`. 
            # In Windows/cross-platform, we rely on timeout and stripping the environment.
            safe_env = {"PATH": os.environ.get("PATH", "")}
            if os.name == "nt":
                for env_var in ["SYSTEMROOT", "WINDIR", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"]:
                    if env_var in os.environ:
                        safe_env[env_var] = os.environ[env_var]
            else:
                for env_var in ["LANG", "LC_ALL", "HOME"]:
                    if env_var in os.environ:
                        safe_env[env_var] = os.environ[env_var]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds, env=safe_env)
            
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
