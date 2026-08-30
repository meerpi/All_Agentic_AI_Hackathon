from typing import Any, Dict, Optional
import httpx
from agent.tools.base import BaseTool


class ActionDispatcherTool(BaseTool):
    name = "action_dispatcher"
    description = "Triggers external webhooks, REST APIs, system webhooks, and automated external actions."

    def run(
        self,
        target_url: Optional[str] = None,
        url: Optional[str] = None,
        method: str = "POST",
        payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        final_url = target_url or url or kwargs.get("webhook_url") or ""
        data_payload = payload or kwargs.get("data") or {"event": "TASKMASTER_ACTION_TRIGGERED", "status": "OK"}
        
        if final_url and (final_url.startswith("http://") or final_url.startswith("https://")):
            try:
                with httpx.Client(timeout=10.0) as client:
                    if method.upper() == "POST":
                        res = client.post(final_url, json=data_payload, headers=headers)
                    elif method.upper() == "PUT":
                        res = client.put(final_url, json=data_payload, headers=headers)
                    elif method.upper() == "PATCH":
                        res = client.patch(final_url, json=data_payload, headers=headers)
                    elif method.upper() == "DELETE":
                        res = client.delete(final_url, headers=headers)
                    else:
                        res = client.get(final_url, headers=headers)

                    is_ok = res.is_success
                    return {
                        "target_url": final_url,
                        "status_code": res.status_code,
                        "dispatched": is_ok,
                        "status": "DELIVERED" if is_ok else "FAILED",
                        "response_preview": str(res.text[:200]),
                        **({} if is_ok else {"error": f"HTTP {res.status_code}: {res.text[:200]}"})
                    }
            except Exception as err:
                return {
                    "target_url": final_url,
                    "dispatched": False,
                    "status": "FAILED",
                    "status_code": 500,
                    "error": str(err)
                }
        
        return {
            "target_url": final_url,
            "dispatched": False,
            "status": "FAILED",
            "status_code": 400,
            "error": "Invalid or missing target_url. URL must start with http:// or https://"
        }
