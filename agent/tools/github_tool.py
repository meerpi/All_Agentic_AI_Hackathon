import json
import logging
import os
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional
from agent.tools.base import BaseTool
from agent.models import ToolCallResult

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
        **kwargs: Any,
    ) -> Dict[str, Any]:
        
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise ValueError("GITHUB_TOKEN environment variable is required.")
            
        owner = os.environ["GITHUB_OWNER"]
        repo = os.environ["GITHUB_REPO"]

        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"
        self.headers = {
            "Authorization": f"Bearer {token}",
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
            raise ValueError(f"Unknown action: {action}")

    def _make_request(self, method: str, url: str, data: Optional[Dict] = None) -> Any:
        req = urllib.request.Request(url, method=method, headers=self.headers)
        if data is not None:
            req.data = json.dumps(data).encode("utf-8")
        
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))

    def create_pull_request(self, title: str, body: str, head: str, base: str) -> Dict[str, Any]:
        url = f"{self.base_url}/pulls"
        data = {"title": title, "body": body, "head": head, "base": base}
        return self._make_request("POST", url, data)

    def list_issues(self, state: Optional[str] = None, labels: Optional[List[str]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/issues?"
        params = []
        if state:
            params.append(f"state={state}")
        if labels:
            params.append(f"labels={','.join(labels)}")
        url += "&".join(params)
        
        issues = self._make_request("GET", url)
        return {"action": "list_issues", "issues": issues}

    def create_issue(self, title: str, body: str, labels: Optional[List[str]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/issues"
        data = {"title": title, "body": body}
        if labels:
            data["labels"] = labels
        return self._make_request("POST", url, data)

    def manage_branch(self, branch: str, sha: Optional[str] = None) -> Dict[str, Any]:
        if sha:
            # Create branch
            url = f"{self.base_url}/git/refs"
            data = {"ref": f"refs/heads/{branch}", "sha": sha}
            return self._make_request("POST", url, data)
        else:
            # Get branch
            url = f"{self.base_url}/branches/{branch}"
            return self._make_request("GET", url)
