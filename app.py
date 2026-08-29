import logging
from typing import Any, Dict, List
import os
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from agent.config import settings
from agent.models import TaskGoal, WorkflowPlan, ExecutionTrace
from agent.orchestrator import TaskmasterOrchestrator
from agent.tools.registry import registry

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))
logger = logging.getLogger("taskmaster.api")

app = FastAPI(
    title="Taskmaster Autonomous Agent Engine API",
    description="Backend AI Agent API powered by Gemini 3.5 & Google GenAI SDK for multi-step workflow automation.",
    version="1.0.0"
)

# Enable CORS for frontend client integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static web dashboard UI
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

orchestrator = TaskmasterOrchestrator()


@app.get("/", include_in_schema=False)
def read_root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Taskmaster API Server is Running. Visit /docs for OpenAPI specifications."}



@app.get("/api/health", summary="Google Cloud Run Health Check Endpoint")
def health_check():
    return {
        "status": "HEALTHY",
        "agent": "Taskmaster Autonomous Agent Engine",
        "model": settings.GEMINI_MODEL,
        "mock_mode": settings.MOCK_GEMINI,
        "registered_tools_count": len(registry.list_tools())
    }


@app.get("/api/agent/tools", summary="List Registered Agent Tools")
def list_tools():
    return {
        "tools": registry.list_tools()
    }


@app.post("/api/agent/run", response_model=WorkflowPlan, summary="Submit Task Goal & Trigger Autonomous Workflow")
def run_workflow(task_goal: TaskGoal):
    try:
        logger.info(f"Received goal: {task_goal.goal}")
        plan = orchestrator.create_plan(task_goal)
        executed_plan = orchestrator.execute_workflow(plan.workflow_id)
        return executed_plan
    except Exception as e:
        logger.error(f"Error executing workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agent/status/{workflow_id}", response_model=WorkflowPlan, summary="Fetch Workflow Status & Artifacts")
def get_workflow_status(workflow_id: str):
    workflow = orchestrator.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")
    return workflow


@app.get("/api/agent/traces/{workflow_id}", summary="Fetch Reasoning Chain Telemetry Traces")
def get_workflow_traces(workflow_id: str):
    traces = orchestrator.get_traces(workflow_id)
    return {
        "workflow_id": workflow_id,
        "trace_count": len(traces),
        "traces": traces
    }


@app.get("/api/agent/workflows", summary="List All Active and Historical Workflows")
def list_workflows():
    return {
        "workflows": list(orchestrator.workflows.values())
    }


@app.post("/api/agent/approve/{workflow_id}", summary="Approve Paused Human-in-the-Loop Step")
def approve_step(workflow_id: str):
    workflow = orchestrator.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")
    
    # Resume execution if paused
    executed = orchestrator.execute_workflow(workflow_id)
    return {
        "message": "Step approved and workflow execution resumed.",
        "workflow": executed
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)

