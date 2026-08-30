import os
import sys
from unittest.mock import patch, MagicMock
from agent.tools.registry import registry
from agent.tools.action_dispatcher import ActionDispatcherTool
from agent.tools.github_tool import GithubTool
from agent.tools.google_calendar_tool import GoogleCalendarTool
from agent.tools.docker_sandbox import DockerSandboxTool
from agent.multi_agent.sub_agents import CriticSubAgent
from agent.multi_agent.council_orchestrator import MultiAgentCouncilOrchestrator, CouncilOrchestrator
from agent.evals import TrajectoryEvaluator, TrajectoryEvaluationReport
from agent.models import WorkflowPlan, PlanStep, WorkflowStatus, StepStatus


def test_action_dispatcher_rejects_missing_url():
    """Verify ActionDispatcherTool does NOT silently fallback to httpbin.org when url is omitted."""
    tool = ActionDispatcherTool()
    res = tool.run()
    assert res["status"] == "FAILED"
    assert res["dispatched"] is False
    assert res["status_code"] == 400
    assert "Invalid or missing target_url" in res["error"]


def test_github_tool_parameter_validation():
    """Verify GithubTool safely requires token and repo coordinates without unhandled KeyErrors."""
    tool = GithubTool()
    
    # Missing token
    with patch.dict(os.environ, {}, clear=True):
        res = tool.run(action="list_issues")
        assert res["status"] == "FAILED"
        assert "GITHUB_TOKEN is required" in res["error"]

    # Missing owner/repo
    with patch.dict(os.environ, {"GITHUB_TOKEN": "mock_token"}, clear=True):
        res = tool.run(action="list_issues")
        assert res["status"] == "FAILED"
        assert "Missing required GitHub repository parameters" in res["error"]

    # Explicit kwargs
    with patch.dict(os.environ, {"GITHUB_TOKEN": "mock_token"}, clear=True), \
         patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = b'[{"number": 1, "title": "Issue 1"}]'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = tool.run(action="list_issues", owner="test_owner", repo="test_repo")
        assert res["status"] == "SUCCESS"
        assert len(res["issues"]) == 1


def test_google_calendar_relative_time_parsing():
    """Verify GoogleCalendarTool handles relative keywords like 'next_available' and 'tomorrow'."""
    tool = GoogleCalendarTool()
    
    iso1 = tool._parse_iso("next_available")
    assert "T" in iso1
    
    iso2 = tool._parse_iso("tomorrow")
    assert "T" in iso2

    iso3 = tool._parse_iso("now")
    assert "T" in iso3


def test_docker_sandbox_uses_sys_executable():
    """Verify python_sandbox runs with the active interpreter."""
    tool = DockerSandboxTool()
    res = tool.run(code="import sys; print(sys.executable)")
    assert res["status"] == "SUCCESS"
    assert sys.executable in res["stdout"]


def test_critic_sub_agent_dynamic_audit_reporting():
    """Verify CriticSubAgent reports real rule counts and honest violation status."""
    agent = CriticSubAgent()
    
    # Missing deliverables case
    resp = agent.execute(
        task_payload={},
        accumulated_context={
            "intelligence_insights": {"action_items": ["Task 1", "Task 2"]},
            "engineering_insights": {"tickets": []},
            "doc_insights": {},
            "ops_insights": {}
        }
    )
    
    assert resp.insights["verdict"] == "REVISION_REQUIRED"
    assert resp.insights["audit_score"] < 100
    assert len(resp.insights["violations"]) >= 3
    assert "Audit flagged" in resp.reasoning


def test_trajectory_evaluator_string_status_defense():
    """Verify TrajectoryEvaluator handles deserialized string statuses without AttributeError."""
    evaluator = TrajectoryEvaluator(None)
    
    # Create workflow plan with string-like status
    step1 = PlanStep(step_number=1, description="Step 1", tool_name="data_extractor", reasoning="Test reasoning 1", status=StepStatus.COMPLETED)
    step2 = PlanStep(step_number=2, description="Step 2", tool_name="validator", reasoning="Test reasoning 2", status=StepStatus.FAILED)
    
    plan = WorkflowPlan(
        workflow_id="wf_test",
        goal="Test goal",
        steps=[step1, step2],
        status=WorkflowStatus.FAILED
    )
    
    # Force status to raw string to test defense
    step1.status = "COMPLETED"  # type: ignore
    step2.status = "FAILED"     # type: ignore
    
    report = evaluator._deterministic_eval(plan, steps_data=[], tools_used=["data_extractor", "validator"])
    assert isinstance(report, TrajectoryEvaluationReport)
    assert report.workflow_id == "wf_test"
    assert report.overall_score > 0
    assert report.plan_adherence.reasoning == "1/2 steps completed"


def test_media_controller_guardrail_url_playback():
    """Verify check_execution_rails allows youtube_play with 'url' or 'video_url' instead of rigidly demanding 'query'."""
    from agent.guardrails import check_execution_rails

    # Playback with URL should pass
    res_url = check_execution_rails("media_controller", {"action": "youtube_play", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    assert res_url.passed is True
    assert len(res_url.violations) == 0

    # Playback with search query should pass
    res_query = check_execution_rails("media_controller", {"action": "youtube_play", "query": "Lex Fridman podcast"})
    assert res_query.passed is True
    assert len(res_query.violations) == 0

    # Playback with empty args should fail
    res_empty = check_execution_rails("media_controller", {"action": "youtube_play"})
    assert res_empty.passed is False
    assert "Missing required parameter" in res_empty.violations[0]


def test_jira_search_jql_migration():
    """Verify JiraTool._list_issues calls the modern /rest/api/3/search/jql endpoint."""
    from agent.tools.jira_tool import JiraTool
    import json

    tool = JiraTool()
    with patch.dict(os.environ, {"JIRA_URL": "https://mockjira.atlassian.net", "JIRA_EMAIL": "test@example.com", "JIRA_API_TOKEN": "token"}, clear=True), \
         patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "issues": [
                {"key": "KAN-101", "fields": {"summary": "Task 1", "status": {"name": "To Do"}, "priority": {"name": "High"}, "assignee": None}}
            ]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = tool.run(action="list_issues", project_key="KAN")
        assert res["action"] == "list_issues"
        assert res["count"] == 1
        assert res["issues"][0]["key"] == "KAN-101"

        # Verify request targeted /rest/api/3/search/jql with POST
        req = mock_urlopen.call_args[0][0]
        assert "/rest/api/3/search/jql" in req.full_url
        assert req.method == "POST"

