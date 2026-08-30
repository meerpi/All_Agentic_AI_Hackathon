"""
Jira Project Management Tool — Autonomous Issue & Sprint Task Creation.

Supports:
1. Live Atlassian Jira Cloud REST API (if JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN are set).
2. Zero-Cost Autonomous Issue Board (persists structured tickets with issue keys like PROD-101,
   acceptance criteria, story points, and assignees to local DB & Google Sheets).
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error
import base64
from dotenv import load_dotenv

load_dotenv()

from agent.tools.base import BaseTool

logger = logging.getLogger("taskmaster.tools.jira")

_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
_JIRA_STORE_PATH = os.path.join(_STORAGE_DIR, "jira_issues.json")


class JiraTool(BaseTool):
    name = "jira"
    description = (
        "Creates, manages, and tracks Jira engineering tasks, user stories, and bugs. "
        "Actions: create_issue, create_tasks_bulk, list_issues, get_issue."
    )

    def __init__(self):
        os.makedirs(_STORAGE_DIR, exist_ok=True)
        if not os.path.exists(_JIRA_STORE_PATH):
            with open(_JIRA_STORE_PATH, "w") as f:
                json.dump([], f)

    def _load_issues(self) -> List[Dict[str, Any]]:
        try:
            with open(_JIRA_STORE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_issues(self, issues: List[Dict[str, Any]]):
        try:
            with open(_JIRA_STORE_PATH, "w") as f:
                json.dump(issues, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save Jira issues store: {e}")

    def run(
        self,
        action: str = "create_issue",
        summary: Optional[str] = None,
        description: Optional[str] = None,
        issue_type: str = "Task",
        priority: str = "Medium",
        assignee: Optional[str] = None,
        story_points: Optional[int] = None,
        components: Optional[List[str]] = None,
        tasks: Optional[List[Dict[str, Any]]] = None,
        project_key: Optional[str] = None,
        issue_key: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        action = action.lower()
        active_project_key = os.getenv("JIRA_PROJECT_KEY") or project_key or "KAN"

        if action == "create_issue":
            return self._create_issue(
                project_key=active_project_key,
                summary=summary or "Untitled Task",
                description=description or "",
                issue_type=issue_type,
                priority=priority,
                assignee=assignee or "Unassigned",
                story_points=story_points or 3,
                components=components or []
            )
        elif action == "create_tasks_bulk":
            return self._create_tasks_bulk(
                project_key=active_project_key,
                tasks=tasks or []
            )
        elif action == "list_issues":
            return self._list_issues(project_key)
        elif action == "get_issue":
            return self._get_issue(issue_key or "")
        elif action == "transition_issue":
            return self._transition_issue(issue_key or "", kwargs.get("status_name") or kwargs.get("transition_id") or "")
        else:
            return {"error": f"Unknown action '{action}'. Supported: create_issue, create_tasks_bulk, list_issues, get_issue, transition_issue"}

    # ---------- Implementation Methods ----------

    def _create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str,
        priority: str,
        assignee: str,
        story_points: int,
        components: List[str]
    ) -> Dict[str, Any]:
        """Create a single Jira issue (via REST API or zero-cost local board)."""
        jira_url = os.getenv("JIRA_URL")
        jira_email = os.getenv("JIRA_EMAIL")
        jira_token = os.getenv("JIRA_API_TOKEN")

        # 1. Try Live Jira Cloud REST API if credentials exist
        if jira_url and jira_email and jira_token:
            try:
                auth_str = base64.b64encode(f"{jira_email}:{jira_token}".encode("utf-8")).decode("utf-8")
                api_endpoint = f"{jira_url.rstrip('/')}/rest/api/3/issue"
                payload = {
                    "fields": {
                        "project": {"key": project_key},
                        "summary": summary,
                        "description": {
                            "type": "doc",
                            "version": 1,
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]
                        },
                        "issuetype": {"name": issue_type},
                        "priority": {"name": priority}
                    }
                }
                req = urllib.request.Request(
                    api_endpoint,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Basic {auth_str}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    }
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    created_key = res_data.get("key", f"{project_key}-101")
                    return {
                        "action": "create_issue",
                        "issue_key": created_key,
                        "url": f"{jira_url.rstrip('/')}/browse/{created_key}",
                        "summary": summary,
                        "assignee": assignee,
                        "status": "CREATED_IN_JIRA_CLOUD"
                    }
            except Exception as e:
                logger.warning(f"Jira Cloud API call failed: {e}. Falling back to zero-cost Jira board.")

        # 2. Zero-Cost Autonomous Issue Board
        issues = self._load_issues()
        next_num = 100 + len(issues) + 1
        generated_key = f"{project_key}-{next_num}"
        created_at = datetime.now(timezone.utc).isoformat()

        issue_obj = {
            "key": generated_key,
            "project": project_key,
            "summary": summary,
            "description": description,
            "issue_type": issue_type,
            "priority": priority,
            "assignee": assignee,
            "story_points": story_points,
            "components": components,
            "status": "TO DO",
            "created_at": created_at,
            "url": f"https://jira.internal/{project_key}/browse/{generated_key}"
        }

        issues.append(issue_obj)
        self._save_issues(issues)

        logger.info(f"Successfully generated Jira issue {generated_key}: '{summary}' assigned to {assignee}")

        return {
            "action": "create_issue",
            "issue_key": generated_key,
            "summary": summary,
            "issue_type": issue_type,
            "priority": priority,
            "assignee": assignee,
            "story_points": story_points,
            "url": issue_obj["url"],
            "status": "CREATED",
            "mode": "AUTONOMOUS_JIRA_BOARD"
        }

    def _create_tasks_bulk(self, project_key: str, tasks: Any) -> Dict[str, Any]:
        """Create multiple Jira issues in batch from a parsed action item list."""
        parsed_tasks = []
        if isinstance(tasks, str):
            try:
                loaded = json.loads(tasks)
                if isinstance(loaded, list):
                    parsed_tasks = loaded
                elif isinstance(loaded, dict):
                    parsed_tasks = [loaded]
            except Exception:
                parsed_tasks = [{"summary": tasks, "assignee": "Unassigned"}]
        elif isinstance(tasks, dict):
            parsed_tasks = [tasks]
        elif isinstance(tasks, list):
            parsed_tasks = tasks

        if not parsed_tasks:
            raise ValueError("Input tasks list cannot be empty for bulk creation.")

        created_issues = []
        for t in parsed_tasks:
            if not isinstance(t, dict):
                t = {"summary": str(t)}
            res = self._create_issue(
                project_key=project_key,
                summary=t.get("summary") or t.get("task") or t.get("name") or "Untitled Task",
                description=t.get("description") or t.get("acceptance_criteria") or "",
                issue_type=t.get("issue_type", "Task"),
                priority=t.get("priority", "Medium"),
                assignee=t.get("assignee", "Unassigned"),
                story_points=t.get("story_points", 3),
                components=t.get("components", [])
            )
            created_issues.append(res)

        return {
            "action": "create_tasks_bulk",
            "total_created": len(created_issues),
            "issues": created_issues,
            "issue_keys": [i["issue_key"] for i in created_issues],
            "status": "SUCCESS"
        }

    def _list_issues(self, project_key: str) -> Dict[str, Any]:
        """List all issues in project."""
        issues = self._load_issues()
        filtered = [i for i in issues if i.get("project") == project_key]
        return {
            "action": "list_issues",
            "project": project_key,
            "count": len(filtered),
            "issues": filtered
        }

    def _get_issue(self, issue_key: str) -> Dict[str, Any]:
        """Get single issue details."""
        issues = self._load_issues()
        for i in issues:
            if i.get("key") == issue_key:
                return {"action": "get_issue", "issue": i, "status": "FOUND"}
        return {"action": "get_issue", "issue_key": issue_key, "status": "NOT_FOUND"}

    def _transition_issue(self, issue_key: str, transition: str) -> Dict[str, Any]:
        """Change issue status via transition."""
        if not issue_key or not transition:
            raise ValueError("issue_key and status/transition_id are required.")

        jira_url = os.getenv("JIRA_URL")
        jira_email = os.getenv("JIRA_EMAIL")
        jira_token = os.getenv("JIRA_API_TOKEN")

        if jira_url and jira_email and jira_token:
            try:
                auth_str = base64.b64encode(f"{jira_email}:{jira_token}".encode("utf-8")).decode("utf-8")
                api_endpoint = f"{jira_url.rstrip('/')}/rest/api/3/issue/{issue_key}/transitions"
                
                payload = {
                    "transition": {
                        "id": transition if transition.isdigit() else transition
                    }
                }
                
                req = urllib.request.Request(
                    api_endpoint,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Basic {auth_str}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    return {
                        "action": "transition_issue",
                        "issue_key": issue_key,
                        "status": "TRANSITIONED_IN_JIRA_CLOUD"
                    }
            except Exception as e:
                logger.warning(f"Jira Cloud API transition failed: {e}. Falling back to zero-cost Jira board.")

        # Zero-Cost Autonomous Issue Board fallback
        issues = self._load_issues()
        for i in issues:
            if i.get("key") == issue_key:
                i["status"] = transition
                self._save_issues(issues)
                return {
                    "action": "transition_issue",
                    "issue_key": issue_key,
                    "new_status": transition,
                    "status": "TRANSITIONED",
                    "mode": "AUTONOMOUS_JIRA_BOARD"
                }

        return {"action": "transition_issue", "issue_key": issue_key, "status": "NOT_FOUND"}
