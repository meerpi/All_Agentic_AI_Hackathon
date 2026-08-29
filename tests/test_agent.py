import pytest
from fastapi.testclient import TestClient
from app import app
from agent.models import TaskGoal, WorkflowStatus, StepStatus
from agent.orchestrator import TaskmasterOrchestrator
from agent.tools.registry import registry

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert data["registered_tools_count"] == 5


def test_tools_list_endpoint():
    response = client.get("/api/agent/tools")
    assert response.status_code == 200
    tools = response.json()["tools"]
    tool_names = [t["name"] for t in tools]
    assert "data_extractor" in tool_names
    assert "db_manager" in tool_names
    assert "action_dispatcher" in tool_names
    assert "report_generator" in tool_names
    assert "validator" in tool_names


def test_individual_tool_executions():
    # Data Extractor
    extractor = registry.get_tool("data_extractor")
    res1 = extractor.execute(raw_content="Error log line 104 in auth module")
    assert res1.success is True
    assert "extracted_fields" in res1.data

    # DB Manager
    db = registry.get_tool("db_manager")
    res2 = db.execute(action="upsert", collection="test_col", data={"key": "val"})
    assert res2.success is True
    assert res2.data["status"] == "SUCCESS"

    # Action Dispatcher
    dispatcher = registry.get_tool("action_dispatcher")
    res3 = dispatcher.execute(target_url="https://example.com/webhook", payload={"ping": "pong"})
    assert res3.success is True
    assert res3.data["dispatched"] is True

    # Report Generator
    reporter = registry.get_tool("report_generator")
    res4 = reporter.execute(report_title="Test Report")
    assert res4.success is True
    assert "markdown_content" in res4.data

    # Validator
    val = registry.get_tool("validator")
    res5 = val.execute(criteria=["no_errors"])
    assert res5.success is True
    assert res5.data["is_valid"] is True


def test_orchestrator_end_to_end():
    orchestrator = TaskmasterOrchestrator()
    goal = TaskGoal(goal="Audit cluster logs, save records, and alert team")
    
    plan = orchestrator.create_plan(goal)
    assert plan.workflow_id is not None
    assert len(plan.steps) > 0

    executed = orchestrator.execute_workflow(plan.workflow_id)
    assert executed.status == WorkflowStatus.COMPLETED
    assert executed.summary is not None
    assert executed.final_artifact is not None

    traces = orchestrator.get_traces(plan.workflow_id)
    assert len(traces) > 0
    event_types = [t.event_type for t in traces]
    assert "PLAN_GENERATED" in event_types
    assert "WORKFLOW_FINISHED" in event_types


def test_api_run_workflow_endpoint():
    payload = {
        "goal": "Process customer lead intake form and generate executive summary",
        "context": {"priority": "HIGH", "source": "web_form"}
    }
    response = client.post("/api/agent/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["workflow_id"] is not None
    assert len(data["steps"]) >= 4

    # Verify status endpoint
    wf_id = data["workflow_id"]
    status_resp = client.get(f"/api/agent/status/{wf_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["workflow_id"] == wf_id

    # Verify traces endpoint
    trace_resp = client.get(f"/api/agent/traces/{wf_id}")
    assert trace_resp.status_code == 200
    assert trace_resp.json()["trace_count"] > 0
