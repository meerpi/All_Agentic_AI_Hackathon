"""
Test Suite for Strands Agents SDK Integration and Taskmaster Pro (Track 2: Professional Agents).
"""

import asyncio
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from agent.strands_bridge import (
    SAFE_TOOLS,
    SENSITIVE_TOOLS,
    StrandsToolRegistry,
    TaskmasterProAgent,
    adapt_basetool_to_strands,
    build_professional_council_graph,
    hitl_manager,
    strands_tool_registry,
)
from agent.streaming import strands_workflow_sse_generator
from agent.tools.base import BaseTool
from agent.tools.validator import ValidatorTool
from app import app

client = TestClient(app)


def test_tool_adapter_wrapping():
    """Verify BaseTool converts to Strands @tool with schema and metadata."""
    validator = ValidatorTool()
    strands_tool = adapt_basetool_to_strands(validator)

    assert hasattr(strands_tool, "tool_spec")
    spec = strands_tool.tool_spec
    assert spec["name"] == "validator"
    assert "inputSchema" in spec
    assert "json" in spec["inputSchema"]
    properties = spec["inputSchema"]["json"]["properties"]
    assert "data_to_validate" in properties
    assert "criteria" in properties

    # Test execution through the wrapped Strands callable
    res = strands_tool(data_to_validate={"status": "OK"}, criteria=["status_ok"])
    assert isinstance(res, dict)
    assert res.get("is_valid") is True


def test_tool_adapter_exception_resilience():
    """Verify tool execution exceptions are safely caught and wrapped."""
    class BrokenTool(BaseTool):
        name = "broken_tool"
        description = "Tool that throws unexpected error"

        def run(self, **kwargs):
            raise RuntimeError("Database connection timed out during execution")

    broken = BrokenTool()
    strands_broken = adapt_basetool_to_strands(broken)
    res = strands_broken()
    assert isinstance(res, dict)
    assert res.get("status") == "FAILED"
    assert "Database connection timed out" in str(res.get("error"))


def test_tool_registry_categorization():
    """Verify safe vs. sensitive tool separation for HITL governance."""
    pro_tools = strands_tool_registry.get_professional_tools()
    assert len(pro_tools) >= 8

    names = [t.tool_spec["name"] for t in pro_tools]
    assert "jira" in names
    assert "github" in names
    assert "slack" in names
    assert "data_extractor" in names

    safe_names = strands_tool_registry.get_safe_tool_names()
    sensitive_names = strands_tool_registry.get_sensitive_tool_names()

    assert "data_extractor" in safe_names
    assert "validator" in safe_names
    assert "github" in sensitive_names
    assert "jira" in sensitive_names


def test_all_professional_tools_callable():
    """Verify each tool in the curated professional suite is invocable."""
    pro_tools = strands_tool_registry.get_professional_tools()
    for tool_fn in pro_tools:
        name = tool_fn.tool_spec["name"]
        # Invoke with empty kwargs to test resilience
        res = tool_fn()
        assert isinstance(res, dict), f"Tool {name} did not return a dict"


def test_hitl_approval_lifecycle():
    """Verify registration, approval, and rejection lifecycle in HITL manager."""
    wid = "test-workflow-123"

    # Register approval request
    req = hitl_manager.register_approval_request(
        workflow_id=wid,
        tool_name="github",
        tool_args={"action": "create_pr", "title": "feat: release v1"},
        reason="Creating public Pull Request",
    )
    assert req.status == "PENDING"
    assert req.risk_level == "HIGH"
    assert req.interrupt_id in [p.interrupt_id for p in hitl_manager.get_pending(wid)]

    # Approve request
    approved = hitl_manager.approve(req.interrupt_id)
    assert approved is not None
    assert approved.status == "APPROVED"
    assert len(hitl_manager.get_pending(wid)) == 0

    # Register another request and reject it
    req2 = hitl_manager.register_approval_request(
        workflow_id=wid,
        tool_name="slack",
        tool_args={"action": "post_message", "channel": "#announcements"},
        reason="Posting to company-wide channel",
    )
    rejected = hitl_manager.reject(req2.interrupt_id, reason="Hold off until morning")
    assert rejected is not None
    assert rejected.status == "REJECTED"
    assert rejected.reason == "Hold off until morning"


def test_professional_agent_initialization():
    """Verify TaskmasterProAgent initializes with Strands primitives."""
    agent = TaskmasterProAgent(enable_hitl=True, workflow_id="test-agent-init")
    assert agent.agent is not None
    assert len(agent.tools) >= 8
    assert agent.hitl_handler is not None
    assert "Taskmaster Pro" in agent.agent.system_prompt


def test_professional_agent_run_mocked():
    """Verify TaskmasterProAgent.run returns structured results."""
    agent = TaskmasterProAgent(enable_hitl=True, workflow_id="test-agent-run")
    
    mock_result = MagicMock()
    mock_result.output = "Decomposed PRD into 3 Jira tasks."
    mock_result.stop_reason = "completed"
    mock_result.tool_calls = []

    from strands import Agent
    with patch.object(Agent, "__call__", return_value=mock_result):
        res = agent.run("Decompose PRD into tasks")
        assert res["status"] == "COMPLETED"
        assert res["workflow_id"] == "test-agent-run"
        assert "Decomposed PRD" in res["output"]


def test_multiagent_council_graph():
    """Verify Graph Multi-Agent Council architecture and node dependencies."""
    graph = build_professional_council_graph()
    assert graph.id.startswith("council_")
    assert len(graph.nodes) == 4
    expected_nodes = {"spec_specialist", "engineering_qa", "operations_release", "comms_specialist"}
    assert set(graph.nodes.keys()) == expected_nodes
    assert len(graph.edges) == 3
    assert len(graph.entry_points) == 1


def test_api_health_strands_capabilities():
    """Verify /api/health exposes Strands SDK and Professional Track capabilities."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "strands_agents_sdk_v1_55" in data["capabilities"]
    assert "professional_agents_track" in data["capabilities"]


def test_api_strands_tools_endpoint():
    """Verify GET /api/strands/tools returns the full tool catalog."""
    response = client.get("/api/strands/tools")
    assert response.status_code == 200
    data = response.json()
    assert data["engine"] == "strands-agents-v1.55"
    assert data["total_tools"] >= 8
    tool_names = [t["name"] for t in data["tools"]]
    assert "jira" in tool_names
    assert "github" in tool_names


def test_api_strands_approval_endpoints():
    """Verify REST approval and rejection endpoints."""
    # Register pending item directly
    req = hitl_manager.register_approval_request(
        workflow_id="api-test-wf",
        tool_name="jira",
        tool_args={"action": "create_issue", "summary": "Fix login bug"},
        reason="Creating production Jira issue",
    )

    # List pending
    list_res = client.get("/api/strands/pending?workflow_id=api-test-wf")
    assert list_res.status_code == 200
    assert list_res.json()["total_pending"] >= 1

    # Approve via API
    approve_res = client.post(f"/api/strands/approve/{req.interrupt_id}")
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "SUCCESS"
    assert approve_res.json()["approval"]["status"] == "APPROVED"


def test_api_strands_reject_endpoint():
    """Verify REST rejection endpoint with custom reason."""
    req = hitl_manager.register_approval_request(
        workflow_id="api-reject-wf",
        tool_name="gmail",
        tool_args={"action": "send_email", "to": "client@example.com"},
        reason="Send email to external client",
    )

    reject_res = client.post(
        f"/api/strands/reject/{req.interrupt_id}",
        json={"reason": "Need QA signoff first"},
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "SUCCESS"
    assert "Need QA signoff first" in reject_res.json()["message"]


def test_api_strands_decision_404():
    """Verify 404 response on unknown interrupt IDs."""
    res_approve = client.post("/api/strands/approve/nonexistent-id-999")
    assert res_approve.status_code == 404

    res_reject = client.post("/api/strands/reject/nonexistent-id-999", json={"reason": "test"})
    assert res_reject.status_code == 404


def test_api_strands_run_endpoint():
    """Verify POST /api/strands/run endpoint."""
    with patch("agent.strands_bridge.TaskmasterProAgent.run") as mock_run:
        mock_run.return_value = {
            "workflow_id": "wf-strands-run",
            "status": "COMPLETED",
            "output": "Tasks created in Jira and verified.",
            "tool_calls": [{"name": "jira", "args": {"action": "create"}}],
            "pending_approvals": [],
        }

        response = client.post(
            "/api/strands/run",
            json={
                "goal": "Prepare Jira sprint and run smoke tests",
                "enable_hitl": True,
                "mode": "agent",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "COMPLETED"
        assert "Tasks created" in data["output"]


@pytest.mark.asyncio
async def test_strands_sse_generator():
    """Verify strands_workflow_sse_generator yields well-formed SSE lines."""
    events = []
    # Test generator with a brief goal
    async for sse_chunk in strands_workflow_sse_generator("Quick unit test goal", enable_hitl=False):
        events.append(sse_chunk)

    assert len(events) >= 2
    assert any("event: workflow_started" in e for e in events)
    assert any("event: done" in e for e in events)
    for e in events:
        assert e.endswith("\n\n")


def test_api_strands_stream_endpoint():
    """Verify GET /api/strands/stream endpoint establishes an SSE connection."""
    response = client.get("/api/strands/stream?goal=TestGoal&enable_hitl=false")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    content = response.text
    assert "event: workflow_started" in content
    assert "event: done" in content
