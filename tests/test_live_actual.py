"""
Live, End-to-End System Tests for Taskmaster Professional Agents (Track 2).
Uses Strands Agents SDK and real Gemini API with real tool execution (NO MOCKS).
"""

import asyncio
import os
import sys
import pytest
from fastapi.testclient import TestClient

from agent.strands_bridge import (
    SAFE_TOOLS,
    SENSITIVE_TOOLS,
    StrandsToolRegistry,
    TaskmasterProAgent,
    build_professional_council_graph,
    hitl_manager,
    strands_tool_registry,
)
from agent.streaming import strands_workflow_sse_generator
from app import app

client = TestClient(app)


def test_live_tools_real_execution():
    """Verify each core tool executes real operations on the live system."""
    # 1. Real Python code execution in sandbox
    sandbox = strands_tool_registry.get_tool("python_sandbox")
    assert sandbox is not None, "python_sandbox tool not registered"
    calc_code = "import math\nvals = [10, 20, 30, 40, 50]\nprint(f'MEAN={sum(vals)/len(vals):.1f}')\nprint(f'SUMSQ={sum(x**2 for x in range(100))}')"
    res_sandbox = sandbox(code=calc_code)
    assert res_sandbox.get("status") == "SUCCESS"
    assert "MEAN=30.0" in res_sandbox.get("stdout", "")
    assert "SUMSQ=328350" in res_sandbox.get("stdout", "")

    # 2. Real SQLite database operations
    db = strands_tool_registry.get_tool("db_manager")
    assert db is not None, "db_manager tool not registered"
    res_db_create = db(action="execute", query="CREATE TABLE IF NOT EXISTS live_system_audit (id INTEGER PRIMARY KEY, component TEXT, status TEXT)")
    assert res_db_create.get("status") == "COMPLETED"

    res_db_insert = db(action="execute", query="INSERT INTO live_system_audit (component, status) VALUES ('auth_service', 'OPERATIONAL')")
    assert res_db_insert.get("status") == "COMPLETED"

    # 3. Real schema & criteria validation
    val = strands_tool_registry.get_tool("validator")
    assert val is not None, "validator tool not registered"
    res_val = val(
        data_to_validate={"service": "auth_service", "p95_latency_ms": 42, "error_rate": 0.0008},
        criteria=["p95_under_100ms", "error_rate_under_1pct"],
    )
    assert res_val.get("is_valid") is True
    assert res_val.get("recommendation") == "PROCEED"

    # 4. Real executive report generation
    rep = strands_tool_registry.get_tool("report_generator")
    assert rep is not None, "report_generator tool not registered"
    res_rep = rep(
        title="Live System Integrity Audit",
        summary="Automated verification of core telemetry and compliance bounds.",
        sections=[{"heading": "Telemetry", "content": "All services operating within latency limits."}],
        format="markdown",
    )
    assert "Live System Integrity Audit" in res_rep.get("markdown_content", "")
    assert res_rep.get("sections_count") >= 1

    # 5. Real Playwright Chromium headless navigation
    browser = strands_tool_registry.get_tool("browser_controller")
    assert browser is not None, "browser_controller tool not registered"
    res_nav = browser(action="navigate", url="https://example.com")
    assert res_nav.get("status") == "SUCCESS"
    assert "Example Domain" in res_nav.get("title", "")


def test_live_hitl_governance_lifecycle():
    """Verify Human-In-The-Loop gate intercepts sensitive operations with approval tokens."""
    workflow_id = "live-hitl-wf-1"

    # Register sensitive operation
    req = hitl_manager.register_approval_request(
        workflow_id=workflow_id,
        tool_name="github",
        tool_args={"action": "create_pull_request", "title": "feat: release v2.0"},
        reason="Creating public pull request on GitHub repository",
    )
    assert req.status == "PENDING"
    assert req.risk_level == "HIGH"
    assert req.interrupt_id in [p.interrupt_id for p in hitl_manager.get_pending(workflow_id)]

    # Approve via HITL manager
    approved = hitl_manager.approve(req.interrupt_id)
    assert approved is not None
    assert approved.status == "APPROVED"
    assert len(hitl_manager.get_pending(workflow_id)) == 0


def test_live_agent_multi_step_autonomous_workflow():
    """Execute real multi-step agent workflow with live Gemini LLM calling real tools."""
    agent = TaskmasterProAgent(enable_hitl=False, workflow_id="live-actual-audit-agent")

    goal = (
        "Perform an autonomous security and data integrity audit: "
        "1. Run a script using python_sandbox to generate a SHA-256 digest of the text 'taskmaster-pro-2026' and print it. "
        "2. Save this audit entry into SQLite using db_manager. "
        "3. Validate the digest format using validator. "
        "4. Summarize the audit results using report_generator."
    )

    result = agent.run(goal)
    assert result["status"] == "COMPLETED"
    assert result["workflow_id"] == "live-actual-audit-agent"
    assert len(result["tool_calls"]) >= 2
    assert len(result["output"]) > 50

    # Verify that python_sandbox or db_manager was one of the tools invoked
    tool_names = [tc["name"] for tc in result["tool_calls"]]
    assert "python_sandbox" in tool_names or "db_manager" in tool_names


@pytest.mark.asyncio
async def test_live_sse_stream_generation():
    """Verify real-time SSE generator produces live streaming events."""
    events = []
    async for sse_chunk in strands_workflow_sse_generator("Quick live streaming verification", enable_hitl=False):
        events.append(sse_chunk)

    assert len(events) >= 2
    assert any("event: workflow_started" in e for e in events)
    assert any("event: done" in e for e in events)
    for e in events:
        assert e.endswith("\n\n")


def test_live_api_health_and_tools():
    """Verify FastAPI server exposes real Strands capabilities and tool catalog."""
    # Health endpoint
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    data_health = res_health.json()
    assert "strands_agents_sdk_v1_55" in data_health["capabilities"]
    assert "professional_agents_track" in data_health["capabilities"]

    # Tools endpoint
    res_tools = client.get("/api/strands/tools")
    assert res_tools.status_code == 200
    data_tools = res_tools.json()
    assert data_tools["engine"] == "strands-agents-v1.55"
    assert data_tools["total_tools"] >= 8
    names = [t["name"] for t in data_tools["tools"]]
    assert "python_sandbox" in names
    assert "db_manager" in names
    assert "validator" in names
    assert "report_generator" in names
