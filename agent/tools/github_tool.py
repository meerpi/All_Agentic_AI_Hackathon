import json
import logging
import os
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional
from agent.tools.base import BaseTool

logger = logging.getLogger("taskmaster.tools.github")


class GithubTool(BaseTool):
    name = "github"
    description = (
        "Interacts with the GitHub API to manage PRs, issues, and branches. "
        "Actions: create_pull_request, list_issues, create_issue, manage_branch."
    )

    def run(
        self,
        action: str = "list_issues",
        title: Optional[str] = None,
        body: Optional[str] = None,
        head: Optional[str] = None,
        base: Optional[str] = None,
        state: Optional[str] = None,
        labels: Optional[List[str]] = None,
        branch: Optional[str] = None,
        sha: Optional[str] = None,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        token: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        auth_token = token or os.environ.get("GITHUB_TOKEN")
        if not auth_token:
            return {
                "action": action,
                "status": "FAILED",
                "error": "GITHUB_TOKEN is required to execute GitHub actions. Set GITHUB_TOKEN in environment or pass token parameter."
            }
            
        target_owner = owner or kwargs.get("github_owner") or os.environ.get("GITHUB_OWNER")
        target_repo = repo or kwargs.get("github_repo") or os.environ.get("GITHUB_REPO")

        if not target_owner or not target_repo:
            return {
                "action": action,
                "status": "FAILED",
                "error": "Missing required GitHub repository parameters: 'owner' and 'repo' must be provided or set via GITHUB_OWNER and GITHUB_REPO."
            }

        self.base_url = f"https://api.github.com/repos/{target_owner}/{target_repo}"
        self.headers = {
            "Authorization": f"Bearer {auth_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }

        action = action.lower()
        if action == "create_pull_request":
            return self.create_pull_request(title or "", body or "", head or "", base or "")
        elif action == "list_issues":
            return self.list_issues(state, labels)
        elif action == "create_issue":
            return self.create_issue(title or "", body or "", labels)
        elif action == "manage_branch":
            return self.manage_branch(branch or "", sha)
        else:
            return {
                "action": action,
                "status": "FAILED",
                "error": f"Unknown action: '{action}'. Supported: create_pull_request, list_issues, create_issue, manage_branch."
            }

    def _make_request(self, method: str, url: str, data: Optional[Dict] = None) -> Any:
        req = urllib.request.Request(url, method=method, headers=self.headers)
        if data is not None:
            req.data = json.dumps(data).encode("utf-8")
        
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(err_body)
                msg = err_json.get("message") or err_body
            except Exception:
                msg = err_body
            logger.error(f"GitHub API HTTPError ({e.code}) on {url}: {msg}")
            return {
                "status": "FAILED",
                "status_code": e.code,
                "error": f"GitHub API Error ({e.code}): {msg}"
            }
        except Exception as e:
            logger.error(f"GitHub API connection error on {url}: {e}")
            return {
                "status": "FAILED",
                "error": f"GitHub API connection error: {str(e)}"
            }

    def create_pull_request(self, title: str, body: str, head: str, base: str) -> Dict[str, Any]:
        url = f"{self.base_url}/pulls"
        data = {"title": title, "body": body, "head": head, "base": base}
        res = self._make_request("POST", url, data)
        if isinstance(res, dict) and res.get("status") == "FAILED":
            return res
        return {"action": "create_pull_request", "status": "SUCCESS", "pull_request": res}

    def list_issues(self, state: Optional[str] = None, labels: Optional[List[str]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/issues?"
        params = []
        if state:
            params.append(f"state={state}")
        if labels:
            params.append(f"labels={','.join(labels)}")
        url += "&".join(params)
        
        issues = self._make_request("GET", url)
        if isinstance(issues, dict) and issues.get("status") == "FAILED":
            return issues
        return {"action": "list_issues", "status": "SUCCESS", "issues": issues}

    def create_issue(self, title: str, body: str, labels: Optional[List[str]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/issues"
        data = {"title": title, "body": body}
        if labels:
            data["labels"] = labels
        res = self._make_request("POST", url, data)
        if isinstance(res, dict) and res.get("status") == "FAILED":
            return res
        return {"action": "create_issue", "status": "SUCCESS", "issue": res}

    def manage_branch(self, branch: str, sha: Optional[str] = None) -> Dict[str, Any]:
        if sha:
            url = f"{self.base_url}/git/refs"
            data = {"ref": f"refs/heads/{branch}", "sha": sha}
            res = self._make_request("POST", url, data)
            if isinstance(res, dict) and res.get("status") == "FAILED":
                return res
            return {"action": "create_branch", "status": "SUCCESS", "result": res}
        else:
            url = f"{self.base_url}/branches/{branch}"
            res = self._make_request("GET", url)
            if isinstance(res, dict) and res.get("status") == "FAILED":
                return res
            return {"action": "get_branch", "status": "SUCCESS", "branch": res}
