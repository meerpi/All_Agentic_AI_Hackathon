from typing import Any, Dict, Optional
import httpx
from agent.tools.base import BaseTool


class ActionDispatcherTool(BaseTool):
    name = "action_dispatcher"
    description = "Triggers external webhooks, REST APIs, system webhooks, and automated external actions."

    def run(
        self,
        target_url: str = "https://httpbin.org/post",
        method: str = "POST",
        payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        data_payload = payload or {"event": "TASKMASTER_ACTION_TRIGGERED", "status": "OK"}
        
        # Perform webhook call simulation or real HTTP call
        if target_url.startswith("http://") or target_url.startswith("https://"):
            try:
                with httpx.Client(timeout=5.0) as client:
                    if method.upper() == "POST":
                        res = client.post(target_url, json=data_payload, headers=headers)
                    else:
                        res = client.get(target_url, headers=headers)
                    return {
                        "target_url": target_url,
                        "status_code": res.status_code,
                        "dispatched": True,
                        "response_preview": str(res.text[:150])
                    }
            except Exception as err:
                return {
                    "target_url": target_url,
                    "dispatched": False,
                    "status_code": 500,
                    "error": str(err)
                }
        
        return {
            "target_url": target_url,
            "dispatched": False,
            "status_code": 400,
            "error": "Invalid or missing target_url"
        }
