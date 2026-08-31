import json
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.a2a import A2AServer, get_agent_card
from agent.config import settings
from agent.database import db
from agent.evals import TrajectoryEvaluator
from agent.inbox_watcher import watcher
from agent.llm_client import GeminiClient
from agent.memory import MemoryManager
from agent.models import ComplexityReport, ExecutionTrace, StepStatus, TaskGoal, WorkflowPlan, WorkflowStatus, ToolCallResult
from agent.multi_agent import MultiAgentCouncilOrchestrator
from agent.orchestrator import TaskmasterOrchestrator
from agent.persistence import persistence
from agent.prd_parser import PRDParser
from agent.security import audit_logger
from agent.streaming import workflow_sse_generator
from agent.task_expansion import TaskExpansionEngine
from agent.time_travel import time_travel
from agent.tools.registry import registry

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))
logger = logging.getLogger("taskmaster.api")

app = FastAPI(
    title="Taskmaster Autonomous Agent Engine API",
    description="Production-grade AI Agent API with DAG execution, real A2A protocol, MCP server exposition, persistent memory, SQLite storage, and live SSE streaming.",
    version="1.0.0",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static and frontend UI
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

orchestrator = TaskmasterOrchestrator()
council_orchestrator = MultiAgentCouncilOrchestrator()
a2a_server = A2AServer(orchestrator=orchestrator, council=council_orchestrator)
memory_mgr = MemoryManager()
expansion_engine = TaskExpansionEngine(GeminiClient())
prd_parser = PRDParser(GeminiClient())


# ── Auth & Session Models ───────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateSessionRequest(BaseModel):
    title: Optional[str] = "New Chat"
    session_id: Optional[str] = None


class RenameSessionRequest(BaseModel):
    title: str


class AddMessageRequest(BaseModel):
    role: str
    content: str
    data: Optional[Dict[str, Any]] = None
    timestamp: Optional[int] = None


def get_current_user(request: Request) -> Dict[str, Any]:
    """Helper to authenticate and extract the current user from Bearer token."""
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token required.")
    
    user = db.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")
    return user


# ── Root, Auth, Chat & Developer Pages ─────────────────────────

@app.get("/", include_in_schema=False)
def read_root():
    """Serves the Hero Landing Page."""
    landing_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(landing_path):
        return FileResponse(landing_path)
    return {"message": "Taskmaster API Server is Running. Visit /docs for OpenAPI specifications."}


@app.get("/auth", include_in_schema=False)
@app.get("/login", include_in_schema=False)
@app.get("/register", include_in_schema=False)
def auth_page():
    """Serves the Sign In / Sign Up Authentication Page."""
    auth_path = os.path.join(frontend_dir, "auth.html")
    if os.path.exists(auth_path):
        return FileResponse(auth_path)
    return RedirectResponse(url="/chat", status_code=302)


@app.get("/chat", include_in_schema=False)
def chat_page():
    """Serves the ChatGPT-Style Conversational Agent UI."""
    chat_path = os.path.join(frontend_dir, "chat.html")
    if os.path.exists(chat_path):
        return FileResponse(chat_path)
    return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.get("/features", include_in_schema=False)
@app.get("/tools", include_in_schema=False)
def features_page():
    """Serves the Features & Tools Showcase Page."""
    features_path = os.path.join(frontend_dir, "features.html")
    if os.path.exists(features_path):
        return FileResponse(features_path)
    return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.get("/architecture", include_in_schema=False)
@app.get("/dag", include_in_schema=False)
def architecture_page():
    """Serves the DAG Engine & Multi-Agent Architecture Page."""
    arch_path = os.path.join(frontend_dir, "architecture.html")
    if os.path.exists(arch_path):
        return FileResponse(arch_path)
    return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.get("/integrations", include_in_schema=False)
def integrations_page():
    """Serves the Ecosystem & Platform Integrations Page."""
    integ_path = os.path.join(frontend_dir, "integrations.html")
    if os.path.exists(integ_path):
        return FileResponse(integ_path)
    return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.get("/hub", include_in_schema=False)
def hub_page():
    """Redirect legacy Hub requests directly to the Chat interface."""
    return RedirectResponse(url="/chat", status_code=302)


@app.get("/api/health", summary="Google Cloud Run Health Check Endpoint")
def health_check():
    return {
        "status": "HEALTHY",
        "agent": "Taskmaster Autonomous Agent Engine",
        "models": {
            "main": settings.MAIN_MODEL,
            "research": settings.RESEARCH_MODEL,
            "fallback": settings.FALLBACK_MODEL,
        },
        "mock_mode": settings.MOCK_GEMINI,
        "registered_tools_count": len(registry.list_tools()),
        "capabilities": [
            "task_dependency_dag",
            "a2a_protocol_compliant",
            "mcp_server_support",
            "persistent_memory",
            "sqlite_multi_user_storage",
            "time_travel_debugging",
            "sse_token_streaming",
            "guardrails_safety_rails",
        ],
    }


@app.post("/api/agent/media/stop", summary="Stop or pause active background browser media playback")
async def stop_media_api():
    """Stops/pauses any running background playback across Playwright or media controllers."""
    try:
        from agent.browser.session_manager import browser_manager
        page = browser_manager._page
        if page:
            await page.evaluate("document.querySelector('video')?.pause()")
        return {"status": "SUCCESS", "message": "Media playback stopped"}
    except Exception as e:
        return {"status": "SUCCESS", "message": str(e)}


# ── Multi-User Authentication & SQLite Chat Storage Endpoints ──

@app.post("/api/auth/register", summary="Register a new user account")
def register_user_api(req: RegisterRequest):
    try:
        res = db.register_user(req.email, req.password, req.full_name)
        return {"status": "SUCCESS", "data": res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@app.post("/api/auth/login", summary="Login user and obtain auth token")
def login_user_api(req: LoginRequest):
    try:
        res = db.authenticate_user(req.email, req.password)
        return {"status": "SUCCESS", "data": res}
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


@app.get("/api/auth/me", summary="Get currently authenticated user profile")
def get_me_api(request: Request):
    user = get_current_user(request)
    return {"status": "SUCCESS", "user": user}


@app.post("/api/auth/logout", summary="Logout and revoke active session token")
def logout_user_api(request: Request):
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        db.logout_token(token)
    return {"status": "SUCCESS", "message": "Logged out successfully."}


@app.get("/api/chat/sessions", summary="Get user's chat sessions from SQLite")
def get_user_sessions_api(request: Request):
    user = get_current_user(request)
    sessions = db.get_user_sessions(user["id"])
    return {"status": "SUCCESS", "sessions": sessions}


@app.post("/api/chat/sessions", summary="Create a new chat session for user in SQLite")
def create_session_api(req: CreateSessionRequest, request: Request):
    user = get_current_user(request)
    session = db.create_session(user["id"], req.title or "New Chat", req.session_id)
    return {"status": "SUCCESS", "session": session}


@app.get("/api/chat/sessions/{session_id}/messages", summary="Get messages for a session from SQLite")
def get_session_messages_api(session_id: str, request: Request):
    user = get_current_user(request)
    messages = db.get_session_messages(session_id, user["id"])
    return {"status": "SUCCESS", "messages": messages}


@app.post("/api/chat/sessions/{session_id}/messages", summary="Save message to SQLite")
def add_session_message_api(session_id: str, req: AddMessageRequest, request: Request):
    user = get_current_user(request)
    msg = db.add_message(session_id, user["id"], req.role, req.content, req.data, req.timestamp)
    return {"status": "SUCCESS", "message": msg}


@app.delete("/api/chat/sessions/{session_id}", summary="Delete chat session from SQLite")
def delete_session_api(session_id: str, request: Request):
    user = get_current_user(request)
    deleted = db.delete_session(session_id, user["id"])
    return {"status": "SUCCESS", "deleted": deleted}


@app.post("/api/chat/sessions/{session_id}/rename", summary="Rename chat session in SQLite")
def rename_session_api(session_id: str, req: RenameSessionRequest, request: Request):
    user = get_current_user(request)
    renamed = db.rename_session(session_id, user["id"], req.title)
    return {"status": "SUCCESS", "renamed": renamed}


# ── A2A Protocol Standard Endpoints ────────────────────────────

@app.get("/.well-known/agent-card.json", summary="A2A AgentCard Discovery (Linux Foundation Standard)")
def agent_card_discovery(request: Request):
    """Returns official AgentCard JSON manifest for external agent discovery."""
    base_url = str(request.base_url).rstrip("/")
    return get_agent_card(base_url)


@app.post("/api/a2a", summary="A2A JSON-RPC 2.0 Endpoint")
async def a2a_jsonrpc_endpoint(request: Request):
    """Handles standard JSON-RPC 2.0 requests (tasks/send, tasks/get, tasks/cancel, skills/list)."""
    try:
        body = await request.json()
        return a2a_server.handle_jsonrpc(body)
    except Exception as e:
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {str(e)}"}}


# ── Core Workflow Endpoints ────────────────────────────────────

@app.get("/api/agent/tools", summary="List Registered Agent Tools")
def list_tools():
    return {"tools": registry.list_tools()}


class ExecuteToolRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]

@app.post("/api/agent/tool/execute", response_model=ToolCallResult, summary="Execute a Specific Tool Directly")
def execute_tool_endpoint(req: ExecuteToolRequest):
    tool = registry.get_tool(req.tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{req.tool_name}' not found")
    try:
        result = tool.execute(req.arguments)
        return result
    except Exception as e:
        logger.error(f"Error executing tool {req.tool_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/agent/run", response_model=WorkflowPlan, summary="Submit Task Goal & Trigger DAG Workflow")
def run_workflow(task_goal: TaskGoal):
    try:
        logger.info(f"Received goal: {task_goal.goal}")
        plan = orchestrator.create_plan(task_goal)
        executed_plan = orchestrator.execute_workflow(plan.workflow_id)
        return executed_plan
    except Exception as e:
        logger.error(f"Error executing workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agent/stream", summary="Real-Time Server-Sent Events (SSE) Workflow Stream")
async def stream_workflow(goal: str, require_approval: bool = False, tag: Optional[str] = None):
    """Streams token chunks, state transitions, and step results in real-time."""
    tags = [tag] if tag else []
    return StreamingResponse(
        workflow_sse_generator(goal, require_approval=require_approval, tags=tags),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/agent/status/{workflow_id}", response_model=WorkflowPlan, summary="Fetch Workflow Status & Artifacts")
def get_workflow_status(workflow_id: str):
    workflow = orchestrator.workflows.get(workflow_id)
    if not workflow:
        data = persistence.load_workflow(workflow_id)
        if data:
            workflow = WorkflowPlan(**data)
        else:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")
    return workflow


@app.get("/api/agent/workflows", summary="List All Workflows with Tag & Status Filtering")
def list_workflows(tag: Optional[str] = Query(None), status: Optional[str] = Query(None)):
    persisted = persistence.list_workflows(status_filter=status, tag_filter=tag)
    return {"total": len(persisted), "workflows": persisted}


@app.get("/api/agent/traces/{workflow_id}", summary="Fetch Reasoning Chain Telemetry Traces")
def get_workflow_traces(workflow_id: str):
    traces = orchestrator.traces.get(workflow_id, [])
    return {"workflow_id": workflow_id, "trace_count": len(traces), "traces": traces}


@app.post("/api/agent/approve/{workflow_id}", summary="Approve Paused Human-in-the-Loop Step")
def approve_step(workflow_id: str):
    try:
        executed = orchestrator.resume_workflow(workflow_id)
        return {"message": "Step approved and workflow execution resumed.", "workflow": executed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/cancel/{workflow_id}", summary="Cancel a Workflow")
def cancel_workflow(workflow_id: str):
    workflow = orchestrator.workflows.get(workflow_id)
    if not workflow:
        data = persistence.load_workflow(workflow_id)
        if data:
            workflow = WorkflowPlan(**data)
        else:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")

    workflow.status = WorkflowStatus.FAILED
    
    # Cancel pending steps
    for step in workflow.steps:
        if step.status in (StepStatus.PENDING, StepStatus.IN_PROGRESS, StepStatus.WAITING_APPROVAL):
            step.status = StepStatus.FAILED
            step.error = "Cancelled by user"
            
    persistence.save_workflow(workflow_id, workflow.model_dump(mode="json"))
    return {"message": "Workflow cancelled.", "workflow": workflow.model_dump(mode="json")}


# ── PRD Parser & Task Expansion Endpoints ──────────────────────

class ParsePRDRequest(BaseModel):
    prd_content: str
    tools_description: Optional[str] = None


@app.post("/api/agent/parse-prd", summary="Parse PRD into Structured Task Graph")
def parse_prd_endpoint(req: ParsePRDRequest):
    try:
        tools_desc = req.tools_description or registry.get_tools_description_prompt()
        result = prd_parser.parse(req.prd_content, tools_desc)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/expand/{workflow_id}/{step_number}", summary="Decompose Task into Subtasks")
def expand_task_endpoint(workflow_id: str, step_number: int, num_subtasks: int = 3):
    workflow = orchestrator.workflows.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")

    step = next((s for s in workflow.steps if s.step_number == step_number), None)
    if not step:
        raise HTTPException(status_code=404, detail=f"Step {step_number} not found.")

    subtasks = expansion_engine.expand_step(step, num_subtasks=num_subtasks)
    persistence.save_workflow(workflow_id, workflow.model_dump(mode="json"))
    return {"parent_step": step_number, "subtasks": [s.model_dump(mode="json") for s in subtasks]}


@app.get("/api/agent/complexity-report/{workflow_id}", response_model=ComplexityReport, summary="Get Fibonacci Complexity Report")
def get_complexity_report(workflow_id: str):
    workflow = orchestrator.workflows.get(workflow_id)
    if not workflow:
        data = persistence.load_workflow(workflow_id)
        if data:
            workflow = WorkflowPlan(**data)
        else:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")

    report = expansion_engine.generate_complexity_report(workflow.steps, workflow_id=workflow_id)
    return report


# ── Cost, Memory & Telemetry Endpoints ─────────────────────────

@app.get("/api/agent/cost-report/{workflow_id}", summary="Get Token Usage and USD Cost Attribution")
def get_cost_report(workflow_id: str):
    workflow = orchestrator.workflows.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")
    return {
        "workflow_id": workflow_id,
        "token_usage": workflow.token_usage.model_dump(mode="json"),
    }


@app.get("/api/agent/memory/search", summary="Search Persistent Episodic & Semantic Memory")
def search_memory_endpoint(query: str):
    return memory_mgr.search_all(query)


@app.get("/api/agent/audit-logs", summary="Fetch Security & Compliance Audit Trail")
def get_audit_logs(limit: int = 50, workflow_id: Optional[str] = None):
    return {"audit_entries": audit_logger.get_entries(workflow_id=workflow_id, limit=limit)}


# ── Time-Travel Debugging Endpoints ────────────────────────────

class ForkWorkflowRequest(BaseModel):
    checkpoint_step_number: int
    modified_inputs: Optional[Dict[str, Any]] = None


@app.get("/api/agent/time-travel/{workflow_id}/history", summary="Get Checkpoint History for Time-Travel")
def get_time_travel_history(workflow_id: str):
    history = time_travel.get_history(workflow_id)
    return {"workflow_id": workflow_id, "checkpoint_count": len(history), "checkpoints": history}


@app.post("/api/agent/time-travel/{workflow_id}/fork", summary="Fork Workflow from Checkpoint")
def fork_workflow_endpoint(workflow_id: str, req: ForkWorkflowRequest):
    try:
        forked = time_travel.fork_from_checkpoint(
            original_workflow_id=workflow_id,
            checkpoint_step_number=req.checkpoint_step_number,
            modified_inputs=req.modified_inputs,
        )
        return {"original_workflow_id": workflow_id, "forked_workflow": forked}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Multi-Agent Council & Pipeline Simulator ───────────────────

@app.post("/api/multi-agent/run", summary="Trigger Hierarchical Multi-Agent Council Workflow")
def run_multi_agent_council(task_goal: TaskGoal):
    try:
        logger.info(f"Triggering Multi-Agent Council for goal: {task_goal.goal}")
        result = council_orchestrator.execute_council(
            goal=task_goal.goal,
            context=task_goal.context,
        )
        return result
    except Exception as e:
        logger.error(f"Error in Multi-Agent Council: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/multi-agent/council-members", summary="List All 5 Specialized Council Members")
def get_council_members():
    return {
        "council_name": "Taskmaster Multi-Agent Council",
        "topology": "Hierarchical Leader-Subagent with Reflexion Loop",
        "members": [
            {
                "name": council_orchestrator.intelligence_agent.name,
                "role": council_orchestrator.intelligence_agent.role.value,
                "description": council_orchestrator.intelligence_agent.description,
                "tools": council_orchestrator.intelligence_agent.scoped_tool_names,
                "icon": "fa-brain",
            },
            {
                "name": council_orchestrator.engineering_agent.name,
                "role": council_orchestrator.engineering_agent.role.value,
                "description": council_orchestrator.engineering_agent.description,
                "tools": council_orchestrator.engineering_agent.scoped_tool_names,
                "icon": "fa-code",
            },
            {
                "name": council_orchestrator.executive_doc_agent.name,
                "role": council_orchestrator.executive_doc_agent.role.value,
                "description": council_orchestrator.executive_doc_agent.description,
                "tools": council_orchestrator.executive_doc_agent.scoped_tool_names,
                "icon": "fa-file-lines",
            },
            {
                "name": council_orchestrator.operations_agent.name,
                "role": council_orchestrator.operations_agent.role.value,
                "description": council_orchestrator.operations_agent.description,
                "tools": council_orchestrator.operations_agent.scoped_tool_names,
                "icon": "fa-calendar-check",
            },
            {
                "name": council_orchestrator.critic_agent.name,
                "role": council_orchestrator.critic_agent.role.value,
                "description": council_orchestrator.critic_agent.description,
                "tools": council_orchestrator.critic_agent.scoped_tool_names,
                "icon": "fa-shield-halved",
            },
        ],
    }


class SimulateInquiryRequest(BaseModel):
    sender: Optional[str] = "Sarah Jenkins <sarah.jenkins@lumina-health.io>"
    subject: Optional[str] = "Inquiry: NextGen Patient Portal & Analytics Dashboard"
    body: Optional[str] = (
        "Hi Anima,\n\n"
        "We came across your work and are looking for a lead full-stack AI engineer "
        "to build our HIPAA-compliant Patient Analytics Dashboard with Gemini-powered medical summaries.\n\n"
        "Scope: React dashboard, FastAPI backend, Firestore DB, Gemini multimodal reports.\n"
        "Timeline: 6 weeks | Budget: $12,500 USD\n\n"
        "Are you available for a 45-minute discovery call this week?\n\n"
        "Best regards,\nSarah Jenkins (VP of Engineering, Lumina Health)"
    )


@app.post("/api/pipeline/simulate", summary="Trigger Simulated Client Inquiry Event")
def simulate_inquiry_endpoint(req: SimulateInquiryRequest):
    try:
        plan = watcher.process_inquiry(
            sender=req.sender or "Client",
            subject=req.subject or "Project Inquiry",
            body=req.body or "",
            source="SIMULATED_WEBHOOK",
        )
        return {
            "status": "SUCCESS",
            "message": "Inquiry processed autonomously across Calendar, Docs, Sheets, and Gmail.",
            "workflow": plan,
        }
    except Exception as e:
        logger.error(f"Error simulating inquiry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pipeline/watcher", summary="Get Background Watcher Status")
def get_watcher_status():
    return watcher.get_status()


@app.post("/api/pipeline/watcher/start", summary="Start Background Inbox Watcher")
def start_watcher():
    watcher.start()
    return {"message": "Background InboxWatcher started.", "status": watcher.get_status()}


@app.post("/api/pipeline/watcher/stop", summary="Stop Background Inbox Watcher")
def stop_watcher():
    watcher.stop()
    return {"message": "Background InboxWatcher stopped.", "status": watcher.get_status()}


# ── Autonomous Browser & Computer Control Endpoints ───────────

from agent.browser.session_manager import browser_manager


@app.post("/api/browser/kill", summary="Emergency Panic Kill Switch for Browser & Desktop Automation")
def emergency_kill_browser():
    """Immediately stops all active browser automation sessions and child contexts."""
    result = browser_manager.emergency_kill()
    return result


@app.post("/api/agent/media/stop", summary="Stop & Silence all background media playback")
@app.post("/api/browser/stop", summary="Stop & Silence all background media playback")
def stop_background_media():
    """Immediately pauses and silences any background audio or video playback in the browser context."""
    try:
        from agent.browser.youtube_driver import YouTubeDriver
        driver = YouTubeDriver()
        result = browser_manager.run_sync(driver.stop_all_media(), timeout=5.0)
        return {"status": "SUCCESS", "message": "All background media playback paused and silenced.", "detail": result}
    except Exception as e:
        logger.warning(f"Error stopping media: {e}")
        return {"status": "SUCCESS", "message": f"Media cleanup triggered: {e}"}


@app.get("/api/browser/status", summary="Get Active Browser Session Status")
def get_browser_status():
    """Returns active URL, title, open pages, and profile status."""
    return browser_manager.run_sync(browser_manager.get_session_status())


@app.get("/api/browser/screenshot", summary="Capture Live Browser Viewport Screenshot")
def get_browser_screenshot(annotated: bool = Query(False, description="Whether to overlay Set-of-Marks badges")):
    """Returns base64 encoded live screenshot of active browser viewport."""
    tool = registry.get_tool("browser_controller")
    if not tool:
        raise HTTPException(status_code=500, detail="browser_controller tool not registered")
    result = tool.execute({"action": "screenshot", "annotated": annotated})
    return result.data


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
