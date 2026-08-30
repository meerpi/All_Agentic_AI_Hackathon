"""
Real-Time Server-Sent Events (SSE) Streaming Engine.

Streams:
- Token chunks during LLM generation
- State transitions (PLANNING -> EXECUTING -> COMPLETED)
- Tool execution start / result events
- Sub-agent council messages in real-time
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict

logger = logging.getLogger("taskmaster.streaming")


class StreamEvent:
    def __init__(self, event_type: str, data: Dict[str, Any]):
        self.event_type = event_type
        self.data = data

    def to_sse(self) -> str:
        return f"event: {self.event_type}\ndata: {json.dumps(self.data, default=str)}\n\n"


async def workflow_sse_generator(goal_text: str, require_approval: bool = False,
                                 tags: list = None) -> AsyncGenerator[str, None]:
    """
    Yields real-time SSE stream events as the orchestrator plans and executes.
    """
    from agent.models import TaskGoal
    from agent.orchestrator import orchestrator

    goal = TaskGoal(goal=goal_text, require_approval=require_approval, tags=tags or [])

    # 1. Start event
    yield StreamEvent("workflow_started", {"goal": goal_text, "require_approval": require_approval}).to_sse()
    await asyncio.sleep(0.05)

    # 2. Planning phase
    yield StreamEvent("phase_transition", {"phase": "PLANNING", "message": "Analyzing goal and generating DAG plan..."}).to_sse()
    await asyncio.sleep(0.05)

    try:
        plan = orchestrator.create_plan(goal)
        yield StreamEvent("plan_generated", {
            "workflow_id": plan.workflow_id,
            "total_steps": len(plan.steps),
            "steps": [
                {
                    "step_number": s.step_number,
                    "description": s.description,
                    "tool_name": s.tool_name,
                    "depends_on": s.depends_on,
                    "complexity_score": s.complexity_score,
                    "risk_level": s.risk_level.value,
                }
                for s in plan.steps
            ],
        }).to_sse()
        await asyncio.sleep(0.05)

        # 3. Execution phase (stream each step)
        yield StreamEvent("phase_transition", {"phase": "EXECUTING", "message": "Executing DAG tasks in topological order..."}).to_sse()

        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def trace_callback(trace):
            loop.call_soon_threadsafe(queue.put_nowait, trace)

        orchestrator.event_callbacks[plan.workflow_id] = trace_callback

        def execute_in_thread():
            try:
                final = orchestrator.execute_plan(plan.workflow_id)
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "completed", "plan": final})
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "error": e})
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "done"})
                
        import threading
        thread = threading.Thread(target=execute_in_thread)
        thread.start()

        final_plan = None
        while True:
            item = await queue.get()
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "completed":
                    final_plan = item["plan"]
                elif item_type == "error":
                    # We could raise it, but since we are yielding, maybe we can raise it
                    # which gets caught by the except block below
                    raise item["error"]
                elif item_type == "done":
                    break
            else:
                # It's an ExecutionTrace
                trace = item
                if trace.event_type == "STEP_STARTED":
                    step = next((s for s in plan.steps if s.step_number == trace.step_number), None)
                    yield StreamEvent("step_started", {
                        "step_number": trace.step_number,
                        "tool_name": trace.details.get("tool"),
                        "description": step.description if step else "",
                    }).to_sse()
                elif trace.event_type == "TOOL_EXECUTION":
                    yield StreamEvent("step_completed", {
                        "step_number": trace.step_number,
                        "tool_name": trace.details.get("tool"),
                        "result": trace.details.get("result"),
                        "duration_ms": trace.details.get("duration_ms"),
                    }).to_sse()
                elif trace.event_type == "STEP_EXCEPTION":
                    yield StreamEvent("step_failed", {
                        "step_number": trace.step_number,
                        "error": trace.details.get("error"),
                    }).to_sse()
                elif trace.event_type == "SELF_CORRECTION":
                    yield StreamEvent("step_correction", {
                        "step_number": trace.step_number,
                        "status": trace.details.get("status"),
                        "result": trace.details.get("result"),
                        "error": trace.details.get("error"),
                    }).to_sse()
                elif trace.event_type == "HITL_PAUSE":
                    yield StreamEvent("workflow_paused", {
                        "step_number": trace.step_number,
                        "tool": trace.details.get("tool"),
                    }).to_sse()

        if plan.workflow_id in orchestrator.event_callbacks:
            del orchestrator.event_callbacks[plan.workflow_id]

        if final_plan:
            # Emit completion
            yield StreamEvent("workflow_completed", {
                "workflow_id": final_plan.workflow_id,
                "status": final_plan.status.value,
                "summary": final_plan.summary,
                "tokens": final_plan.token_usage.model_dump(mode="json"),
                "eval_scores": final_plan.eval_scores,
            }).to_sse()

    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield StreamEvent("workflow_error", {"error": str(e)}).to_sse()

    yield StreamEvent("done", {"message": "Stream complete"}).to_sse()
